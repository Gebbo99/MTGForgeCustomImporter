"""Lettura del testo dalle immagini delle carte (OCR).

Il risultato viene diviso per bande verticali, come su una carta reale:
  - banda titolo (in alto): nome visualizzato e, nei proxy, il nome originale;
  - banda centrale: linea dei tipi, testo delle regole, forza/costituzione;
  - banda inferiore: set e artista, ignorata.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .textutil import clean_title, normalize_ocr

TITLE_BAND = 0.17
FOOTER_BAND = 0.88
ROW_OVERLAP = 0.5
TYPE_WORDS = (
    "creature", "instant", "sorcery", "enchantment", "artifact", "land",
    "planeswalker", "battle", "legendary", "basic", "token", "kindred", "tribal",
    "equipment", "aura", "vehicle", "snow", "world", "conspiracy", "phenomenon",
    "plane", "vanguard", "scheme", "dungeon", "card",
)
_PT_RE = re.compile(r"^\s*\d{1,2}\s*/\s*\d{1,2}\s*$")

_ocr_engine = None
_backend = None


class OcrUnavailable(RuntimeError):
    """Sollevata quando il motore OCR non e' installato."""


def engine():
    """Istanza condivisa del motore OCR (inizializzata alla prima chiamata)."""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
            raise OcrUnavailable(
                "Motore OCR non disponibile: installa rapidocr-onnxruntime."
            ) from exc
        _ocr_engine = RapidOCR()
    return _ocr_engine


def set_backend(backend) -> None:
    """Registra un motore OCR alternativo.

    `backend` e' un callable che accetta il percorso di una immagine e
    restituisce una lista di `(box, testo, score)`, dove `box` sono i quattro
    vertici in pixel: lo stesso formato prodotto da RapidOCR. Serve su Android,
    dove al posto di onnxruntime si usa l'OCR on-device di ML Kit.
    """
    global _backend
    _backend = backend


def run_engine(image_file: str):
    """Esegue il motore OCR attivo (backend registrato o RapidOCR)."""
    if _backend is not None:
        return _backend(image_file)
    return engine()(image_file)


@dataclass
class OcrLine:
    text: str
    score: float
    y_top: float
    y_bottom: float
    height: float
    x_left: float = 0.0
    x_right: float = 0.0

    @property
    def y_center(self) -> float:
        return (self.y_top + self.y_bottom) / 2


@dataclass
class CardReading:
    """Testo estratto da una immagine di carta."""

    image_path: Path
    width: int
    height: int
    title: str = ""
    base_hint: str = ""
    type_line: str = ""
    pt: str = ""
    rules_text: str = ""
    score: float = 0.0
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.title or self.rules_text)


def read_image(image_path: Path, max_width: int = 1600) -> CardReading:
    """Esegue l'OCR su una immagine di carta e ne struttura il contenuto."""
    with Image.open(image_path) as raw:
        image = raw.convert("RGB")
    original_w, original_h = image.size

    scale = 1.0
    if original_w > max_width:
        scale = max_width / original_w
    elif original_w < 600:
        scale = 600 / original_w if original_w else 1.0
    if abs(scale - 1.0) > 0.01:
        image = image.resize((int(original_w * scale), int(original_h * scale)), Image.LANCZOS)

    with tempfile.TemporaryDirectory() as tmp:
        work_file = Path(tmp) / "card.png"
        image.save(work_file)
        result = run_engine(str(work_file))

    boxes = result[0] if isinstance(result, tuple) else result
    width, height = image.size
    reading = CardReading(image_path=image_path, width=original_w, height=original_h)

    if not boxes:
        return reading

    for box, text, score in boxes:
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        top, bottom = min(ys), max(ys)
        reading.lines.append(
            OcrLine(
                text=normalize_ocr(text).strip(),
                score=float(score),
                y_top=top / height,
                y_bottom=bottom / height,
                height=(bottom - top) / height,
                x_left=min(xs) / width,
                x_right=max(xs) / width,
            )
        )
    reading.lines.sort(key=lambda line: line.y_top)

    title_lines = [l for l in reading.lines if l.y_top < TITLE_BAND]
    middle_lines = [l for l in reading.lines if TITLE_BAND <= l.y_top <= FOOTER_BAND]

    if title_lines:
        rows = _title_rows(title_lines)
        if rows:
            reading.title = rows[0]
            if len(rows) > 1:
                reading.base_hint = rows[1]
        reading.score = max((l.score for l in title_lines), default=0.0)

    type_line, pt, rules = _split_middle(middle_lines)
    reading.type_line = type_line
    reading.pt = pt
    reading.rules_text = rules
    return reading


def _title_rows(lines: list[OcrLine]) -> list[str]:
    """Ricompone le righe del titolo: nome visualizzato e, sotto, nome originale.

    L'OCR puo' spezzare una stessa riga in piu' riquadri (e talvolta agganciare
    il costo di mana): i riquadri alla stessa altezza vengono uniti da sinistra
    a destra e ripuliti.
    """
    groups: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda l: (l.y_center, l.x_left)):
        for group in groups:
            if _same_row(group[0], line):
                group.append(line)
                break
        else:
            groups.append([line])
    groups.sort(key=lambda group: min(l.y_top for l in group))

    rows: list[str] = []
    for group in groups:
        text = clean_title(" ".join(l.text for l in sorted(group, key=lambda l: l.x_left)))
        if text:
            rows.append(text)
    return rows


def _same_row(a: OcrLine, b: OcrLine) -> bool:
    top, bottom = max(a.y_top, b.y_top), min(a.y_bottom, b.y_bottom)
    if bottom <= top:
        return False
    smaller = min(a.height, b.height)
    return smaller > 0 and (bottom - top) / smaller >= ROW_OVERLAP


def _split_middle(lines: list[OcrLine]) -> tuple[str, str, str]:
    """Separa la linea dei tipi, la forza/costituzione e il testo delle regole."""
    type_line = ""
    pt = ""
    rules: list[str] = []
    type_seen = False
    for line in lines:
        lowered = line.text.lower()
        if not type_seen and _looks_like_type_line(lowered):
            type_line = line.text
            type_seen = True
            continue
        if _PT_RE.match(line.text):
            if not pt:
                pt = line.text.strip()
            continue
        rules.append(line.text)
    return type_line, pt, " ".join(rules).strip()


def _looks_like_type_line(lowered: str) -> bool:
    if "-" in lowered and sum(word in lowered for word in TYPE_WORDS) >= 1:
        return True
    head = lowered.split(" ")[0] if lowered else ""
    return head in TYPE_WORDS and len(lowered.split()) <= 8


def is_token(reading: "CardReading") -> bool:
    """Vero se l'immagine e' un token.

    I token hanno la linea dei tipi che inizia con "Token" ("Token Creature -
    Beast", "Token Artifact - Food"); le carte normali non lo hanno, anche
    quando creano token nel testo delle regole.
    """
    line = reading.type_line.lower()
    if not line:
        return False
    head = line.split("-")[0]
    return "token" in head.split()
