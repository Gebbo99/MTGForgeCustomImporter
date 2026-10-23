"""Indice dei card script ufficiali di Forge.

Legge res/cardsfolder (cartella sciolta o cardsfolder.zip) ed estrae i campi
che servono al riconoscimento: nome, testo Oracle, tipo, costo, P/T.
L'indice viene salvato su disco e riusato finche' l'archivio non cambia.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .textutil import normalize_for_compare, normalize_plain

CACHE_VERSION = 5


@dataclass(frozen=True)
class CardInfo:
    name: str
    oracle: str
    types: str
    mana_cost: str
    pt: str
    entry: str
    source: str
    # Carta con piu' facce: il nome e' "Fronte // Retro" e Forge pretende che
    # un eventuale flavorName contenga " // ".
    multiface: bool = False
    # Valore della riga "AlternateMode:" dello script (DoubleFaced, Modal,
    # Split, Flip, Adventure, ...): dice come Forge registra il nome della
    # carta, quindi come va scritta la riga [cards] dell'edizione.
    alt_mode: str = ""

    @property
    def oracle_norm(self) -> str:
        return normalize_for_compare(self.oracle)

    @property
    def forge_name(self) -> str:
        """Nome con cui Forge registra la carta (CardRules.getName()).

        Solo le carte Split hanno per nome "Fronte // Retro" (aggregazione
        COMBINE); tutte le altre multi-faccia (DoubleFaced, Modal, Flip, ...)
        sono note col solo nome della faccia anteriore. Usare il nome unito per
        queste ultime fa scartare la riga dell'edizione come "carta mancante" e
        la carta non compare in Forge.
        """
        if not self.multiface or self.alt_mode.strip().lower() == "split":
            return self.name
        return self.name.split(" // ")[0].strip()


def faces_of(card: CardInfo) -> list[str]:
    """Nomi delle singole facce di una carta multi-faccia.

    Il nome di una carta multi-faccia e' "Fronte // Retro": qui si separano le
    due facce (indice 0 = fronte, 1 = retro). Per le carte a faccia singola
    restituisce una lista vuota.
    """
    if not card.multiface:
        return []
    return [part.strip() for part in card.name.split(" // ") if part.strip()]


def _parse_script(text: str) -> dict[str, str]:
    # Le carte multi-faccia hanno due righe "Name:" (fronte, poi retro, separate
    # dalla riga ALTERNATE): Forge le registra con il nome "Fronte // Retro",
    # quindi le si unisce invece di tenere solo l'ultima.
    fields: dict[str, str] = {}
    names: list[str] = []
    current_key: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if ":" in raw_line:
            key, _, value = raw_line.partition(":")
            key = key.strip()
        else:
            key, value = "", raw_line.strip()
        if key == "Name":
            names.append(value.strip())
            current_key = key
        elif key in {"Oracle", "Types", "ManaCost", "PT", "AlternateMode"}:
            fields[key] = value.strip()
            current_key = key
        elif current_key == "Oracle":
            fields["Oracle"] = (fields.get("Oracle", "") + " " + raw_line.strip()).strip()
        else:
            current_key = None
    if names:
        fields["Name"] = " // ".join(names)
    return fields


def _iter_scripts(db_path: Path):
    """Genera (entry, testo) per ogni card script."""
    if db_path.is_file() and db_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(db_path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".txt"):
                    continue
                with archive.open(info) as handle:
                    yield info.filename, handle.read().decode("utf-8", errors="replace")
    else:
        for file in sorted(db_path.glob("**/*.txt")):
            yield file.name, file.read_text(encoding="utf-8", errors="replace")


class CardDB:
    """Collezione dei card script indicizzata per nome."""

    def __init__(self, source: Path, cards: list[CardInfo], settings_path: Path):
        self.source = source
        self.cards = cards
        self._settings_path = settings_path
        self._by_name: dict[str, CardInfo] = {}
        # Indice delle singole facce delle carte multi-faccia: {nome faccia:
        # (carta, indice)}. Serve a collegare le due immagini (fronte e retro)
        # della stessa carta, che l'utente fornisce come file separati.
        self._by_face: dict[str, tuple[CardInfo, int]] = {}
        # Archivio aperto una sola volta: script_text() legge uno script per
        # chiamata e riaprire il .zip ogni volta costa decine di millisecondi
        # (con le centinaia di carte di un set l'attesa congelava l'interfaccia).
        self._archive: zipfile.ZipFile | None = None
        for card in cards:
            key = normalize_plain(card.name)
            self._by_name.setdefault(key, card)
            for index, face in enumerate(faces_of(card)):
                face_key = normalize_plain(face)
                if face_key:
                    self._by_face.setdefault(face_key, (card, index))

    # ---------- caricamento ----------

    @classmethod
    def load(cls, db_path: Path, cache_file: Path) -> "CardDB":
        signature = cls._signature(db_path)
        cached = cls._read_cache(cache_file, signature)
        if cached is not None:
            return cls(db_path, cached, cache_file)

        cards: list[CardInfo] = []
        source_label = str(db_path)
        for entry, text in _iter_scripts(db_path):
            fields = _parse_script(text)
            name = fields.get("Name", "")
            if not name:
                continue
            cards.append(
                CardInfo(
                    name=name,
                    oracle=fields.get("Oracle", ""),
                    types=fields.get("Types", ""),
                    mana_cost=fields.get("ManaCost", ""),
                    pt=fields.get("PT", ""),
                    entry=entry,
                    source=source_label,
                    multiface=" // " in name,
                    alt_mode=fields.get("AlternateMode", ""),
                )
            )
        cards.sort(key=lambda c: c.name)
        db = cls(db_path, cards, cache_file)
        db._write_cache(cache_file, signature)
        return db

    @classmethod
    def load_tokens(cls, scripts_dir: Path) -> "CardDB":
        """Indice degli script dei token (res/tokenscripts).

        I token non sono nell'archivio delle carte: senza questo indice le
        immagini dei token non verrebbero mai riconosciute.
        """
        cards: list[CardInfo] = []
        if scripts_dir.is_dir():
            source_label = str(scripts_dir)
            for entry, text in _iter_scripts(scripts_dir):
                fields = _parse_script(text)
                name = fields.get("Name", "")
                if not name:
                    continue
                cards.append(
                    CardInfo(
                        name=name,
                        oracle=fields.get("Oracle", ""),
                        types=fields.get("Types", ""),
                        mana_cost=fields.get("ManaCost", ""),
                        pt=fields.get("PT", ""),
                        entry=entry,
                        source=source_label,
                        multiface=" // " in name,
                        alt_mode=fields.get("AlternateMode", ""),
                    )
                )
        cards.sort(key=lambda c: c.name)
        return cls(scripts_dir, cards, scripts_dir)

    @staticmethod
    def _signature(db_path: Path) -> dict:
        stat = db_path.stat()
        return {"path": str(db_path), "mtime": int(stat.st_mtime), "size": stat.st_size}

    @classmethod
    def _read_cache(cls, cache_file: Path, signature: dict) -> list[CardInfo] | None:
        if not cache_file.is_file():
            return None
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if data.get("version") != CACHE_VERSION or data.get("signature") != signature:
            return None
        return [
            CardInfo(
                name=item["name"],
                oracle=item.get("oracle", ""),
                types=item.get("types", ""),
                mana_cost=item.get("mana_cost", ""),
                pt=item.get("pt", ""),
                entry=item.get("entry", ""),
                source=item.get("source", ""),
                multiface=item.get("multiface", False),
                alt_mode=item.get("alt_mode", ""),
            )
            for item in data.get("cards", [])
        ]

    def _write_cache(self, cache_file: Path, signature: dict) -> None:
        payload = {
            "version": CACHE_VERSION,
            "signature": signature,
            "cards": [
                {
                    "name": c.name,
                    "oracle": c.oracle,
                    "types": c.types,
                    "mana_cost": c.mana_cost,
                    "pt": c.pt,
                    "entry": c.entry,
                    "source": c.source,
                    "multiface": c.multiface,
                    "alt_mode": c.alt_mode,
                }
                for c in self.cards
            ],
        }
        try:
            cache_file.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
            )
        except OSError:
            pass

    # ---------- consultazione ----------

    def by_name(self, name: str) -> CardInfo | None:
        return self._by_name.get(normalize_plain(name))

    def by_face(self, name: str) -> tuple[CardInfo, int] | None:
        """Carta multi-faccia e indice della faccia con questo nome ufficiale.

        Indice 0 = fronte, 1 = retro. Il nome file di un'immagine porta il nome
        reale della faccia ("Wandering Archaic", "Explore the Vastlands"): con
        questo indice le due immagini della stessa carta vengono collegate.
        """
        key = normalize_plain(name)
        return self._by_face.get(key) if key else None

    def names(self) -> list[str]:
        return [c.name for c in self.cards]

    def script_text(self, card: CardInfo) -> str:
        """Testo integrale dello script, letto on demand."""
        source = Path(card.source)
        if source.is_file() and source.suffix.lower() == ".zip":
            if self._archive is None or Path(self._archive.filename) != source:
                if self._archive is not None:
                    self._archive.close()
                self._archive = zipfile.ZipFile(source)
            return self._archive.read(card.entry).decode("utf-8", errors="replace")
        return (source / card.entry).read_text(encoding="utf-8", errors="replace")
