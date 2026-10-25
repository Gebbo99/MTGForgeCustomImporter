"""Scrittura dei file che Forge legge: edizione, card script e immagini.

Per ogni carta importata il tool:
  1. copia/rinomina l'immagine in Cache/pics/cards/<CODICE>/<Nome>[n].fullborder.<ext>;
  2. aggiunge la riga nella sezione [cards] dell'edizione custom.

Per un re-skin (nome nuovo, regole della carta base) la riga usa il formato
"<NomeBase> @<artista> ${"flavorName": "<NomeNuovo>"}": Forge crea una variante
della carta base con il nome mostrato del re-skin, quindi la nuova arte compare
fra le varianti della carta base (e non come carta a se' stante).

Per ogni token importato il tool:
  1. copia l'immagine in Cache/pics/tokens/<CODICE>/<collector>_<filestem>.<ext>;
  2. crea lo script in custom/tokens/<filestem>.txt rinominandolo col nome letto;
  3. aggiunge la riga nella sezione [tokens] dell'edizione custom;
  4. fa puntare le carte del set che lo creano al nuovo script (TokenScript$).

I token-copia (Eternalize/Embalm) non hanno uno script: Forge copia la carta e
usa un'immagine dedicata, quindi il tool copia solo l'immagine e registra la
riga nella sezione [other] dell'edizione.

Anche gli emblemi dei Planeswalker non hanno uno script: Forge copia l'abilita'
del Planeswalker e li disegna con la chiave "emblem_<slug del nome ufficiale>",
risolta sempre tramite la sezione [other] dell'edizione a cui appartiene la
carta che li ha creati.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import date as date_cls
from pathlib import Path

from PIL import Image

from .carddb import CardDB, CardInfo, faces_of
from .cards import real_name_from_filename
from .i18n import t
from .textutil import normalize_plain

RARITIES = ("L", "C", "U", "R", "M", "S")
_ENTRY_RE = re.compile(r"^\s*(\d*)(\u2605*)\s+([LCURMSlcurms])\s+(.+?)\s*(@.*)?$")
_ARTIST_RE = re.compile(r"@\s*(.+)$")
# Suffisso extraParams delle varianti: " ${"flavorName": "NomeMostrato"}"
_FLAVOR_RE = re.compile(r"\s*\$\{(.*)\}\s*$")
_FLAVOR_NAME_RE = re.compile(r'"flavorName"\s*:\s*"([^"]*)"', re.IGNORECASE)
_FLAVOR_VARIANT_RE = re.compile(r'"variant"\s*:\s*"([^"]*)"', re.IGNORECASE)
# Separatore tra le facce in un flavorName: Forge spezza su "\\s*//\\s*" e
# ricompone con " // " (CardRules.findOrCreateVariantForFlavorName).
_FLAVOR_SPLIT_RE = re.compile(r"\s*//\s*")
_TOKEN_LINE_RE = re.compile(r"^\s*(\d+)\s+([^\s@]+)")
_TOKEN_REF_RE = re.compile(r"(TokenScript\$\s*)([^\s|]+)")
_EMBLEM_WORD_RE = re.compile(r"\bemblem\b", re.IGNORECASE)
_EMBLEM_IMAGE_RE = re.compile(r"Image\$\s*(emblem_[^\s|]+)", re.IGNORECASE)
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


# --------------------------------------------------------------------------
# Edizione
# --------------------------------------------------------------------------


@dataclass
class EditionEntry:
    collector: str
    rarity: str
    name: str
    artist: str = ""
    stars: int = 0
    flavor_name: str = ""
    # Variante esplicita delle righe di arte oltre la prima di un re-skin:
    # '${"variant": "..."}'. Punta alla variante creata dalla riga col
    # flavorName senza rigenerarla (cioe' senza far crashare Forge all'avvio).
    variant: str = ""
    raw: str = ""

    @property
    def card_name(self) -> str:
        """Nome con cui la carta e' nota: il nome mostrato per le varianti."""
        return self.flavor_name or self.name


@dataclass
class Edition:
    path: Path
    code: str = ""
    name: str = ""
    date: str = ""
    type_: str = "Custom"
    meta_extra: list[str] = field(default_factory=list)
    entries: list[EditionEntry] = field(default_factory=list)
    card_raw_lines: list[str] = field(default_factory=list)
    token_lines: list[str] = field(default_factory=list)
    other_sections: list[tuple[str, list[str]]] = field(default_factory=list)

    # ---------- lettura ----------

    @classmethod
    def load(cls, path: Path) -> "Edition":
        edition = cls(path=path)
        if not path.is_file():
            return edition
        section = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1].strip().lower()
                continue
            if section == "metadata":
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key == "Code":
                        edition.code = value
                    elif key == "Name":
                        edition.name = value
                    elif key == "Date":
                        edition.date = value
                    elif key == "Type":
                        edition.type_ = value
                    else:
                        edition.meta_extra.append(stripped)
            elif section == "cards":
                if not stripped:
                    continue
                edition.card_raw_lines.append(line)
                entry = _parse_entry(line)
                if entry:
                    edition.entries.append(entry)
            elif section == "tokens":
                # le righe valide sono "<collector> <script> [@artista]": eventuali
                # righe corrotte da versioni precedenti del tool vengono scartate e
                # ricreate con il formato giusto durante l'importazione.
                if stripped and _TOKEN_LINE_RE.match(line):
                    edition.token_lines.append(line)
            elif section:
                for name, lines in edition.other_sections:
                    if name == section:
                        lines.append(line)
                        break
                else:
                    edition.other_sections.append((section, [line]))
        return edition

    @classmethod
    def create(cls, path: Path, code: str, name: str, date: str | None = None) -> "Edition":
        return cls(path=path, code=code, name=name, date=date or date_cls.today().isoformat())

    # ---------- consultazione ----------

    def art_count(self, card_name: str) -> int:
        target = card_name.strip().lower()
        return sum(1 for entry in self.entries if entry.card_name.strip().lower() == target)

    def find_cards(self, card_name: str) -> list[EditionEntry]:
        """Righe della sezione [cards] registrate con questo nome mostrato."""
        target = card_name.strip().lower()
        return [e for e in self.entries if e.card_name.strip().lower() == target]

    def remove_card(self, entry: EditionEntry) -> None:
        """Rimuove una riga dalla sezione [cards] (elenco e testo da riscrivere)."""
        if entry in self.entries:
            self.entries.remove(entry)
        if entry.raw in self.card_raw_lines:
            self.card_raw_lines.remove(entry.raw)

    def next_collector(self) -> int:
        numbers = [int(entry.collector) for entry in self.entries if entry.collector.isdigit()]
        return (max(numbers) + 1) if numbers else 1

    def names(self) -> set[str]:
        return {entry.card_name.strip().lower() for entry in self.entries}

    # ---------- modifica ----------

    def add_card(
        self,
        card_name: str,
        rarity: str,
        collector: int,
        stars: int = 0,
        artist: str = "",
        flavor_name: str = "",
        variant: str = "",
    ) -> EditionEntry:
        rarity = (rarity or "R").upper()
        if rarity not in RARITIES:
            rarity = "R"
        entry = EditionEntry(
            collector=str(collector),
            rarity=rarity,
            name=card_name,
            artist=artist,
            stars=stars,
            flavor_name=flavor_name,
            variant=variant,
        )
        entry.raw = _format_entry(entry)
        self.entries.append(entry)
        self.card_raw_lines.append(entry.raw)
        return entry

    def next_token_collector(self) -> int:
        numbers: list[int] = []
        for line in self.token_lines:
            match = _TOKEN_LINE_RE.match(line)
            if match:
                numbers.append(int(match.group(1)))
        return (max(numbers) + 1) if numbers else 1

    def token_count(self, filestem: str) -> int:
        target = filestem.strip().lower()
        return sum(
            1 for line in self.token_lines if _token_line_stem(line).lower() == target
        )

    def add_token(self, filestem: str, collector: int, artist: str = "") -> None:
        line = f"{collector} {filestem}"
        if artist:
            line += f" @{artist}"
        self.token_lines.append(line)

    def remove_tokens(self, filestem: str) -> None:
        """Rimuove tutte le righe [tokens] che puntano a questo script."""
        target = filestem.strip().lower()
        self.token_lines = [
            line for line in self.token_lines if _token_line_stem(line).lower() != target
        ]

    # La sezione [other] registra le immagini che non sono ne' carte ne' token
    # con script: in pratica i token-copia creati da Eternalize ed Embalm, che
    # Forge richiama con la image key "eternalize_<nome>"/"embalm_<nome>".

    def other_lines(self) -> list[str]:
        for name, lines in self.other_sections:
            if name == "other":
                return lines
        return []

    def next_other_collector(self) -> int:
        numbers: list[int] = []
        for line in self.other_lines():
            match = _TOKEN_LINE_RE.match(line)
            if match:
                numbers.append(int(match.group(1)))
        return (max(numbers) + 1) if numbers else 1

    def other_count(self, filestem: str) -> int:
        target = filestem.strip().lower()
        return sum(
            1 for line in self.other_lines() if _token_line_stem(line).lower() == target
        )

    def remove_other(self, filestem: str) -> None:
        """Rimuove tutte le righe [other] che puntano a questa immagine."""
        target = filestem.strip().lower()
        for _name, lines in self.other_sections:
            lines[:] = [
                line for line in lines if _token_line_stem(line).lower() != target
            ]

    def add_other(self, filestem: str, collector: int, artist: str = "") -> None:
        line = f"{collector} {filestem}"
        if artist:
            line += f" @{artist}"
        for name, lines in self.other_sections:
            if name == "other":
                lines.append(line)
                return
        self.other_sections.append(("other", [line]))

    def render(self) -> str:
        lines = ["[metadata]"]
        lines.append(f"Code={self.code}")
        lines.append(f"Name={self.name}")
        lines.append(f"Date={self.date or date_cls.today().isoformat()}")
        lines.append(f"Type={self.type_ or 'Custom'}")
        lines.extend(self.meta_extra)
        lines.append("")
        lines.append("[cards]")
        lines.extend(self.card_raw_lines)
        if self.token_lines:
            lines.append("")
            lines.append("[tokens]")
            # Ordine alfabetico per nome token: rende stabile l'output a ogni
            # import (le varianti d'arte restano adiacenti, in ordine di
            # collector) invece di seguire l'ordine di importazione.
            lines.extend(sorted(self.token_lines, key=_token_sort_key))
        for name, section_lines in self.other_sections:
            lines.append("")
            lines.append(f"[{name}]")
            lines.extend(sorted(section_lines, key=_token_sort_key))
        return "\n".join(lines).rstrip() + "\n"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.render(), encoding="utf-8")


def _parse_entry(line: str) -> EditionEntry | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    match = _ENTRY_RE.match(stripped)
    if not match:
        return None
    collector, stars, rarity, rest, tail = match.groups()
    text = f"{rest} {tail}".strip() if tail else rest.strip()
    flavor_name = ""
    variant = ""
    flavor_match = _FLAVOR_RE.search(text)
    if flavor_match:
        extra = flavor_match.group(1)
        name_match = _FLAVOR_NAME_RE.search(extra)
        if name_match:
            flavor_name = name_match.group(1)
        variant_match = _FLAVOR_VARIANT_RE.search(extra)
        if variant_match:
            variant = variant_match.group(1)
        text = text[: flavor_match.start()].strip()
    artist = ""
    artist_match = _ARTIST_RE.search(text)
    if artist_match:
        artist = artist_match.group(1).strip()
        text = text[: artist_match.start()].strip()
    return EditionEntry(
        collector=collector or "",
        rarity=rarity.upper(),
        name=text.strip(),
        artist=artist,
        stars=len(stars),
        flavor_name=flavor_name,
        variant=variant,
        raw=line,
    )


def _format_entry(entry: EditionEntry) -> str:
    prefix = entry.collector + "\u2605" * entry.stars
    text = f"{prefix} {entry.rarity} {entry.name}".strip()
    if entry.artist:
        text += f" @{entry.artist}"
    # Forge rifiuta una riga che dichiari sia flavorName sia variant: la riga
    # della variante esplicita scrive solo il campo variant.
    if entry.variant:
        text += f' ${{"variant": "{entry.variant}"}}'
    elif entry.flavor_name:
        text += f' ${{"flavorName": "{entry.flavor_name}"}}'
    return text


def _token_line_stem(line: str) -> str:
    """Nome dello script (filestem) da una riga della sezione [tokens]."""
    match = _TOKEN_LINE_RE.match(line)
    return match.group(2) if match else ""


def _token_sort_key(line: str) -> str:
    """Chiave per ordinare alfabeticamente le righe delle sezioni token.

    Si ordina per nome dello script; a parita' di script l'ordine di
    scrittura viene mantenuto (l'ordinamento e' stabile), cosi' le varianti
    d'arte dello stesso token restano adiacenti e nell'ordine dei collector.
    """
    match = _TOKEN_LINE_RE.match(line)
    return (match.group(2) if match else line).lower()


def _script_name(path: Path) -> str:
    """Valore della riga "Name:" di uno script, oppure stringa vuota."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.lower().startswith("name:"):
            return line.split(":", 1)[1].strip()
    return ""


def _token_collector_of(edition: Edition, filestem: str) -> int:
    """Numero di collezione di un token gia' registrato nella sezione [tokens]."""
    target = filestem.strip().lower()
    for line in edition.token_lines:
        if _token_line_stem(line).lower() != target:
            continue
        match = _TOKEN_LINE_RE.match(line)
        if match:
            return int(match.group(1))
    return edition.next_token_collector()


def _other_collector_of(edition: Edition, filestem: str) -> int:
    """Numero di collezione di un token-copia gia' registrato in [other]."""
    target = filestem.strip().lower()
    for line in edition.other_lines():
        if _token_line_stem(line).lower() != target:
            continue
        match = _TOKEN_LINE_RE.match(line)
        if match:
            return int(match.group(1))
    return edition.next_other_collector()


def _replace_token_refs(text: str, mapping: dict[str, str]) -> str:
    """Sostituisce gli script dei token richiamati con quelli appena importati."""

    def substitute(match: re.Match[str]) -> str:
        return match.group(1) + mapping.get(match.group(2).lower(), match.group(2))

    return _TOKEN_REF_RE.sub(substitute, text)


def script_name(text: str) -> str:
    """Valore del campo Name: di un card script."""
    for line in text.splitlines():
        if line.lower().startswith("name:"):
            return line.partition(":")[2].strip()
    return ""


def _card_scripts(cards_dir: Path) -> dict[str, Path]:
    """{nome carta (lower): percorso} dei card script custom del set."""
    scripts: dict[str, Path] = {}
    if not cards_dir.is_dir():
        return scripts
    for path in sorted(cards_dir.glob("**/*.txt")):
        try:
            name = script_name(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if name.strip():
            scripts.setdefault(name.strip().lower(), path)
    return scripts


def _card_script_path(cards_dir: Path, card_name: str) -> Path:
    """Script custom di una carta: <cards>/<iniziale>/<slug>.txt (come Forge)."""
    slug = slugify(card_name)
    return cards_dir / slug[:1] / f"{slug}.txt"


def copy_mechanic(text: str) -> str:
    """Prefisso immagine dei token-copia: 'eternalize', 'embalm' oppure ''.

    Eternalize ed Embalm non creano un token con uno script: Forge copia la
    carta e usa un'immagine dedicata, registrata nella sezione [other]
    dell'edizione con il nome "eternalize_<nome carta>"/"embalm_<nome carta>".
    """
    for line in text.splitlines():
        head = line.strip().lower()
        if head.startswith("k:eternalize"):
            return "eternalize"
        if head.startswith("k:embalm"):
            return "embalm"
    return ""


def forge_image_slug(card_name: str) -> str:
    """Trasformazione del nome usata da Forge nelle image key dei token-copia.

    Forge rimuove le virgole, sostituisce gli spazi con "_" e mette tutto in
    minuscolo (apostrofi e trattini restano): "Najarala, Constricting Snake
    Wyvern" diventa "najarala_constricting_snake_wyvern".
    """
    return card_name.replace(",", "").replace(" ", "_").lower()


def emblem_hint(*texts: str) -> bool:
    """Vero se un nome file o un titolo letto indicano un emblema."""
    return any(_EMBLEM_WORD_RE.search(text or "") for text in texts)


def emblem_base_name(text: str) -> str:
    """Nome del Planeswalker da un testo che descrive un emblema.

    Da "Emblem — Chandra, Torch of Defiance" (o dal nome file
    "emblem_chandra_torch_of_defiance") si ricava il nome con cui cercare la
    carta base a cui l'emblema appartiene.
    """
    cleaned = _EMBLEM_WORD_RE.sub("", text or "", count=1)
    cleaned = re.sub(r"[_]+", " ", cleaned)
    return cleaned.strip(" \u2014\u2013-:.,")


def emblem_image_key(card_name: str, base_script: str = "") -> str:
    """Chiave immagine dell'emblema di un Planeswalker.

    Forge disegna l'emblema con la chiave "emblem_<slug>": la prende dal campo
    Image$ dell'abilita' che crea l'emblema oppure, se assente, dal nome
    dichiarato ("Name$ Emblem — Chandra, Torch of Defiance"). Lo slug e' quello
    del nome ufficiale della carta base, perche' il re-skin condivide il suo
    script e quindi la sua chiave.
    """
    match = _EMBLEM_IMAGE_RE.search(base_script or "")
    if match:
        return match.group(1)
    return f"emblem_{forge_image_slug(card_name)}"


def copy_mechanics_in(cards_dir: Path, names: set[str]) -> dict[str, tuple[str, str]]:
    """{nome carta (lower): (prefisso, nome)} per i token-copia del set.

    Eternalize ed Embalm non hanno uno script token: il proxy del token ha di
    norma lo stesso nome della carta che lo crea, quindi si cercano fra gli
    script del set le carte con quel nome e la keyword e si collega l'immagine.
    """
    result: dict[str, tuple[str, str]] = {}
    if not cards_dir.is_dir():
        return result
    for path in sorted(cards_dir.glob("**/*.txt")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        card_name = script_name(text).strip()
        if not card_name or card_name.lower() not in names:
            continue
        prefix = copy_mechanic(text)
        if prefix:
            result.setdefault(card_name.lower(), (prefix, card_name))
    return result


# --------------------------------------------------------------------------
# Importazione
# --------------------------------------------------------------------------


@dataclass
class ImportItem:
    image_path: Path
    base: CardInfo | None
    new_name: str
    rarity: str = "R"
    artist: str = ""
    image_dest: Path | None = None
    script_dest: Path | None = None
    stars: int = 0
    notes: list[str] = field(default_factory=list)
    is_token: bool = False
    # Token-copia (Eternalize/Embalm): non ha uno script, va in [other].
    is_copy: bool = False
    copy_prefix: str = ""
    copy_card: str = ""
    # Emblema di un Planeswalker: solo immagine, registrata in [other].
    is_emblem: bool = False
    # Retro di una carta multi-faccia collegato a mano dall'utente: la base e'
    # gia' quella del fronte, quindi non serve riconoscerlo dal nome del file.
    is_back: bool = False


@dataclass
class ImportOptions:
    crop: bool = False
    width: int = 488
    height: int = 680
    move_within_pics: bool = True


@dataclass
class ImportReport:
    imported: int = 0
    tokens: int = 0
    emblems: int = 0
    scripts_written: int = 0
    images_written: int = 0
    skipped: int = 0
    messages: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.messages.append(message)


def slugify(card_name: str) -> str:
    text = card_name.lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "carta"


def build_token_script(base_script: str, new_name: str) -> str:
    """Copia lo script del token base sostituendo il nome con quello letto.

    Lo script del token cambia solo nel nome: tipi, P/T, parole chiave e
    abilita' restano quelli della base, quindi il token e' giocabile subito.
    """
    output: list[str] = []
    for line in base_script.splitlines():
        if line.lower().startswith("name:"):
            output.append(f"Name:{new_name}")
        else:
            output.append(line)
    text = "\n".join(output)
    return text if text.endswith("\n") else text + "\n"


def token_filestem(base_entry: str, new_name: str) -> str:
    """Nome dello script di un token: <script base>_<nome letto>."""
    return f"{Path(base_entry).stem}_{slugify(new_name)}"


def forge_filename(name: str) -> str:
    """Nome immagine come lo costruisce Forge (ImageUtil.toMWSFilename).

    Forge rimuove gli accenti e i caratteri " / : ? prima di cercare
    l'immagine in cache: se il file viene salvato con il nome originale, per
    i nomi che contengono quei caratteri Forge non lo trova mai.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in stripped if ch not in '"\\/:?')


def java_hash(text: str) -> int:
    """String.hashCode() di Java: intero a 32 bit con segno.

    Forge nomina la variante di un re-skin "FlavorName" + hashCode del nome
    mostrato ricomposto con " // ": il tool deve calcolare lo stesso valore per
    puntare alla variante con ${"variant": ...} invece di ripetere il flavorName.
    """
    result = 0
    for char in text:
        result = (result * 31 + ord(char)) & 0xFFFFFFFF
    return result - 0x100000000 if result >= 0x80000000 else result


def _joined_flavor_name(flavor_name: str) -> str:
    """Nome mostrato come lo ricompone Forge: facce separate da " // ".

    Forge spezza il flavorName su "\\s*//\\s*" e lo ricuce con " // ", quindi
    gli spazi attorno al separatore non contano (CardRules.
    findOrCreateVariantForFlavorName).
    """
    parts = [part.strip() for part in _FLAVOR_SPLIT_RE.split(flavor_name.strip())]
    while parts and parts[-1] == "":
        parts.pop()
    return " // ".join(parts)


def _platform_variant(edition_code: str) -> str:
    """Variante che Forge impone per codice edizione (CardDb.addSetCard).

    I set "OM*" (Alchemy) e "SLX" (UniversesWithin) usano una variante fissa
    invece del nome derivato dall'hash del nome mostrato.
    """
    code = (edition_code or "").strip()
    if code.startswith("OM"):
        return "Alchemy"
    if code == "SLX":
        return "UniversesWithin"
    return ""


def variant_name(flavor_name: str, edition_code: str = "") -> str:
    """Nome della variante creata da Forge per un re-skin (flavorName).

    E' il nome con cui si punta alla variante nelle righe di arte successive
    alla prima, con ${"variant": "..."}: cosi' Forge riusa la variante creata
    dalla riga col flavorName invece di rigenerarla (la rigenerazione ripetuta
    riusa una variante gia' popolata e fa crashare l'avvio di Forge con
    UnsupportedOperationException in CardFace.assignMissingFieldsToVariant).
    """
    platform = _platform_variant(edition_code)
    if platform:
        return platform
    return f"FlavorName{java_hash(_joined_flavor_name(flavor_name))}"


def image_file_name(card_name: str, art_index: int, art_total: int, extension: str) -> str:
    number = "" if art_total <= 1 else str(art_index)
    return f"{forge_filename(card_name)}{number}.fullborder{extension}"


def _face_key(card: CardInfo) -> str:
    """Chiave con cui si riconosce la stessa carta multi-faccia.

    Si usa il nome e non la entry: la stessa carta puo' comparire in piu' set
    (quindi con piu' entry) e fronte e retro devono abbinarsi comunque.
    """
    return normalize_plain(card.name)


class Importer:
    """Esegue materialmente l'importazione di un lotto di carte."""

    def __init__(
        self,
        db: CardDB,
        custom_dir: Path,
        pics_dir: Path,
        tokens_dir: Path | None = None,
        token_pics_dir: Path | None = None,
    ):
        self.db = db
        self.custom_dir = custom_dir
        self.pics_dir = pics_dir
        self.tokens_dir = tokens_dir or custom_dir / "tokens"
        self.token_pics_dir = token_pics_dir or pics_dir.parent / "tokens"

    def run(
        self,
        items: list[ImportItem],
        edition_path: Path,
        edition_code: str,
        edition_name: str,
        options: ImportOptions | None = None,
    ) -> ImportReport:
        options = options or ImportOptions()
        report = ImportReport()
        edition = Edition.load(edition_path)
        if edition.code == "":
            edition.code = edition_code
        if edition.name == "":
            edition.name = edition_name
        edition.code = edition.code or edition_code

        # Righe presenti prima di questo import: la pulizia delle righe superate
        # agisce solo su queste. Le righe scritte adesso non vanno toccate,
        # altrimenti un lotto i cui nomi vengono letti in modo leggermente
        # diverso (es. refuso OCR su una sola immagine) cancellerebbe le righe
        # e le immagini scritte poco prima.
        pre_existing = list(edition.entries)

        code = edition.code.strip() or edition_code
        pics_target = self.pics_dir / code
        cards_dir = self.custom_dir / "cards"
        pics_target.mkdir(parents=True, exist_ok=True)
        collapse_extensions(pics_target)
        collapse_extensions(self.token_pics_dir / code)

        card_items = [item for item in items if not item.is_token and not item.is_emblem]
        token_items = [item for item in items if item.is_token and not item.is_emblem]
        emblem_items = [item for item in items if item.is_emblem]

        # Le carte multi-faccia arrivano come due immagini distinte (fronte e
        # retro). Il retro non e' una carta a se': viene abbinato al fronte
        # della stessa carta base e riscritto per ogni arte del fronte.
        card_items, backs_by_base, used_backs = self._split_faces(card_items)

        # Quante immagini hanno lo stesso nome mostrato in questo lotto: piu' di
        # una significa che l'utente sta importando piu' varianti insieme.
        totals: dict[str, int] = {}
        for item in card_items:
            key = item.new_name.strip().lower()
            if key:
                totals[key] = totals.get(key, 0) + 1

        art_seen: dict[str, int] = {}
        for item in card_items:
            name = item.new_name.strip()
            key = name.lower()
            if not name:
                report.skipped += 1
                report.log(t("gen.skipped_card_name", name=item.image_path.name))
                continue
            if not item.base:
                report.skipped += 1
                report.log(t("gen.skipped_card_base", name=item.image_path.name))
                continue
            art_seen[key] = art_seen.get(key, 0) + 1
            art_total = totals.get(key, 1)
            art_index = art_seen[key]
            item.stars = art_index - 1
            # Nome della carta base: unito per le multi-faccia ("Fronte // Retro").
            base_name = item.base.name.strip()
            # Nome con cui Forge registra la carta nella riga [cards]: per una
            # multi-faccia non Split e' il solo nome della faccia anteriore.
            row_name = item.base.forge_name

            # Carta multi-faccia: il nome mostrato deve essere "Fronte // Retro".
            # Il retro puo' arrivare come immagine a parte (abbinata tramite il
            # nome reale nel file), altrimenti va scritto per intero dal nome.
            faces = faces_of(item.base)
            back: ImportItem | None = None
            if faces:
                if " // " in name:
                    display = name
                else:
                    back = self._pick_back(backs_by_base, item.base, art_index, used_backs)
                    if back is None:
                        report.skipped += 1
                        report.log(
                            t("gen.skipped_multiface", name=item.image_path.name, base=item.base.name)
                        )
                        continue
                    display = f"{name} // {back.new_name.strip()}"
            else:
                display = name

            # Re-skin: la riga usa le regole della carta base e il nome nuovo come
            # flavorName, cosi' Forge mostra la nuova arte fra le varianti della
            # carta base invece che come carta a se' stante.
            flavor_name = "" if display.lower() == base_name.lower() else display

            # Nome file dell'immagine del fronte: per una multi-faccia Forge lo
            # cerca col solo nome della faccia anteriore ("Fio and Levania"), non
            # col nome mostrato unito ("Fio and Levania // Explore Memories"), che
            # verrebbe salvato con gli spazi al posto del separatore.
            image_name = display.split(" // ")[0].strip() if faces else display

            # Variante con cui questa importazione registra il re-skin. Serve
            # anche a riconoscere come superate le righe di un'importazione
            # precedente: quelle oltre la prima arte hanno solo ${"variant":
            # ...} e quindi un nome mostrato pari al nome della carta base, per
            # cui non venivano individuate e restavano nell'edizione (facendo
            # slittare gli indici d'arte e rompendo le immagini in Forge).
            active_variant = variant_name(flavor_name, code) if flavor_name else ""

            if art_total == 1:
                # Una sola immagine con questo nome: re-import idempotente. Se la
                # carta esiste gia' la riga viene aggiornata e l'immagine riusata,
                # senza accumulare copie duplicate ad ogni ri-importazione.
                existing = edition.find_cards(display)
                collector = (
                    int(existing[0].collector)
                    if existing and existing[0].collector.isdigit()
                    else edition.next_collector()
                )
                self._drop_stale_cards(
                    edition,
                    pics_target,
                    pre_existing,
                    display,
                    {base_name, row_name},
                    faces,
                    active_variant,
                )
                self._remove_legacy_front_images(pics_target, display, image_name)
                self._remove_numbered_variants(pics_target, image_name)
                if faces:
                    self._remove_numbered_variants(pics_target, faces[1])
                item.image_dest = self._place_image(
                    item, pics_target, 1, 1, options, report, name=image_name
                )
                if back is not None:
                    self._place_back_image(
                        back, pics_target, faces[1], 1, 1, options, report
                    )
                edition.add_card(
                    row_name, item.rarity, collector, 0, item.artist, flavor_name=flavor_name
                )
                if flavor_name:
                    item.notes.append(t("gen.variant_of", base=row_name, name=display))
                    if self.db.by_name(name) is not None:
                        item.notes.append(t("gen.name_official"))
                else:
                    item.notes.append(t("gen.same_rules"))
            else:
                # Piu' immagini con lo stesso nome importate insieme: ognuna
                # diventa una variante (arte) della stessa carta.
                if art_seen[key] == 1:
                    self._drop_stale_cards(
                        edition,
                        pics_target,
                        pre_existing,
                        display,
                        {base_name, row_name},
                        faces,
                        active_variant,
                    )
                    self._remove_legacy_front_images(pics_target, display, image_name)
                    self._ensure_numbered(pics_target, image_name)
                    if faces:
                        self._ensure_numbered(pics_target, faces[1])
                collector = edition.next_collector()
                item.image_dest = self._place_image(
                    item, pics_target, art_index, art_total, options, report, name=image_name
                )
                if back is not None:
                    self._place_back_image(
                        back, pics_target, faces[1], art_index, art_total, options, report
                    )
                # Forge ricrea (e riusa) la variante quando piu' righe portano lo
                # stesso flavorName: dalla seconda arte in poi si punta con
                # ${"variant": ...} alla variante creata dalla prima, evitando il
                # crash UnsupportedOperationException all'avvio di Forge.
                row_flavor = flavor_name
                row_variant = ""
                if flavor_name and art_index > 1:
                    row_flavor = ""
                    row_variant = active_variant
                edition.add_card(
                    row_name,
                    item.rarity,
                    collector,
                    item.stars,
                    item.artist,
                    flavor_name=row_flavor,
                    variant=row_variant,
                )
                if flavor_name:
                    item.notes.append(
                        t("gen.variant_of_art", base=row_name, name=display, index=art_index, total=art_total)
                    )
                else:
                    item.notes.append(t("gen.same_rules"))
            if back is not None:
                item.notes.append(t("gen.face_pair", back=back.new_name.strip()))
            report.imported += 1

        self._report_orphan_backs(backs_by_base, used_backs, report)

        copy_mechanics = self._copy_mechanics(edition, cards_dir)
        token_refs = self._place_tokens(
            token_items, edition, code, options, report, copy_mechanics
        )
        self._rewire_token_refs(edition, cards_dir, token_refs, report)
        self._place_emblems(emblem_items, edition, code, options, report)

        edition.save()
        report.log(t("gen.edition_updated", path=edition.path))
        return report

    # ---------- carte multi-faccia ----------

    def _split_faces(
        self, items: list[ImportItem]
    ) -> tuple[list[ImportItem], dict[str, list[ImportItem]], set[int]]:
        """Separa i retro delle carte multi-faccia dalle altre immagini.

        Il retro di un proxy multi-faccia e' un file a parte che porta il nome
        reale della faccia posteriore ("Explore the Vastlands"): qui viene
        riconosciuto e raccolto per carta base, cosi' non finisce nel ciclo
        normale (dove verrebbe preso per una variante a se' stante).

        Un retro collegato a mano dall'utente (is_back) non passa dal nome del
        file: la base e' gia' quella del fronte scelto, quindi si usa quella.
        """
        normal: list[ImportItem] = []
        backs: dict[str, list[ImportItem]] = {}
        for item in items:
            if item.is_back:
                if item.base is not None:
                    backs.setdefault(_face_key(item.base), []).append(item)
                else:
                    normal.append(item)
                continue
            lookup = self._face_lookup(item)
            if (
                lookup is not None
                and lookup[1] == 1
                and item.base is not None
                and _face_key(item.base) == _face_key(lookup[0])
            ):
                backs.setdefault(_face_key(item.base), []).append(item)
            else:
                normal.append(item)
        return normal, backs, set()

    def _face_lookup(self, item: ImportItem) -> tuple[CardInfo, int] | None:
        """Carta multi-faccia e indice della faccia indicata dal nome file."""
        if self.db is None:
            return None
        real = real_name_from_filename(item.image_path)
        if not real:
            return None
        return self.db.by_face(real)

    @staticmethod
    def _pick_back(
        backs: dict[str, list[ImportItem]],
        base: CardInfo,
        art_index: int,
        used: set[int],
    ) -> ImportItem | None:
        """Retro da abbinare a questa arte del fronte.

        Con un solo retro importato lo si usa per tutte le arti (l'arte cambia
        solo sul fronte); con piu' retro si abbina per ordine.
        """
        available = backs.get(_face_key(base))
        if not available:
            return None
        back = available[0] if len(available) == 1 else available[min(art_index - 1, len(available) - 1)]
        used.add(id(back))
        return back

    @staticmethod
    def _report_orphan_backs(
        backs: dict[str, list[ImportItem]], used: set[int], report: ImportReport
    ) -> None:
        """Segnala i retro importati senza il fronte corrispondente."""
        for items in backs.values():
            for item in items:
                if id(item) not in used:
                    report.skipped += 1
                    report.log(
                        t("gen.skipped_back_only", name=item.image_path.name, base=item.base.name)
                    )

    def _place_back_image(
        self,
        back: ImportItem,
        pics_target: Path,
        back_name: str,
        art_index: int,
        art_total: int,
        options: ImportOptions,
        report: ImportReport,
    ) -> None:
        """Scrive il retro col nome ufficiale della faccia posteriore.

        Forge cerca il retro col nome ufficiale ("Explore the Vastlands"), non
        col nome mostrato; il numero segue l'arte, cosi' ogni arte del fronte ha
        il suo retro (con un solo retro fornito il file viene duplicato).
        """
        self._place_image(
            back, pics_target, art_index, art_total, options, report, name=back_name
        )

    @staticmethod
    def _stale_cards(
        entries: list[EditionEntry],
        display: str,
        row_names: set[str],
        faces: list[str],
        variant: str = "",
    ) -> list[EditionEntry]:
        """Righe superate da un import precedente della stessa carta mostrata.

        Oltre alla riga con lo stesso nome mostrato (idempotenza normale) si
        recuperano quelle scritte da versioni precedenti del tool con un nome
        diverso per la stessa carta: per una carta multi-faccia l'identita' del
        re-skin e' la faccia anteriore, quindi una riga col solo nome del fronte
        (o con la stessa carta base ma un nome superato) e' una copia stantia.
        Senza la pulizia Forge la mostra come carta a se', collegata alla vecchia
        carta base e priva del retro.

        ``row_names`` elenca i nomi carta base ammessi: quello con cui Forge
        registra la carta adesso e quello usato dalle versioni precedenti.

        ``variant`` e' la variante con cui si registra adesso il re-skin: le
        righe oltre la prima arte di un re-skin hanno solo ``${"variant": ...}``
        e il loro nome mostrato resta quello della carta base, quindi vanno
        riconosciute dal nome della variante per non restare nell'edizione.

        Si cerca solo fra le righe indicate (quelle presenti prima dell'import):
        le righe scritte adesso non sono mai superate.
        """
        target = display.strip().lower()
        row_targets = {name.strip().lower() for name in row_names if name.strip()}
        variant = variant.strip()
        # Identita' del re-skin: la faccia anteriore del nome mostrato, cioe' il
        # nome custom del fronte ("FronteCustom // RetroCustom" -> "FronteCustom").
        front = display.split(" // ")[0].strip().lower()
        stale: list[EditionEntry] = []
        for entry in entries:
            name = entry.card_name.strip().lower()
            if (
                name == target
                or (faces and name.split(" // ")[0].strip() == front)
                or (faces and entry.name.strip().lower() in row_targets)
                or (variant and entry.variant.strip() == variant)
            ):
                stale.append(entry)
        return stale

    def _drop_stale_cards(
        self,
        edition: Edition,
        pics_target: Path,
        pre_existing: list[EditionEntry],
        display: str,
        row_names: set[str],
        faces: list[str],
        variant: str = "",
    ) -> None:
        """Rimuove le righe superate della carta e le immagini che usavano."""
        target = display.strip().lower()
        for entry in self._stale_cards(
            pre_existing, display, row_names, faces, variant
        ):
            edition.remove_card(entry)
            if entry.variant.strip():
                # Riga-variante superata: le immagini che usava portano il nome
                # mostrato, cioe' lo stesso che riscrive adesso l'importazione,
                # quindi non vanno cancellate col nome della carta base.
                continue
            if entry.card_name.strip().lower() != target:
                self._remove_card_images(pics_target, entry.card_name)

    # ---------- immagini ----------

    def _remove_numbered_variants(self, pics_target: Path, card_name: str) -> None:
        """Elimina le immagini numerate (Nome1, Nome2, ...) di una carta.

        Quando una carta torna ad avere una sola arte resta solo
        "Nome.fullborder.ext": senza questa pulizia i file numerati di import
        precedenti resterebbero orfani nella cache.
        """
        prefix = forge_filename(card_name)
        pattern = re.compile(re.escape(prefix) + r"\d+\.fullborder\.[a-z0-9]+$", re.IGNORECASE)
        if not pics_target.is_dir():
            return
        for path in pics_target.iterdir():
            if path.is_file() and pattern.match(path.name):
                try:
                    path.unlink()
                except OSError:
                    pass

    def _remove_legacy_front_images(
        self, pics_target: Path, display: str, image_name: str
    ) -> None:
        """Elimina le immagini del fronte salvate col nome mostrato unito.

        Versioni precedenti del tool salvavano il fronte di una multi-faccia col
        nome completo ("Fio and Levania  Explore Memories1.fullborder.jpg", col
        separatore ridotto a spazi): ora l'immagine usa il solo nome della faccia
        anteriore, quindi i file col vecchio nome resterebbero orfani nella cache.
        """
        if forge_filename(display) == forge_filename(image_name):
            return
        self._remove_card_images(pics_target, display)

    def _remove_card_images(self, pics_target: Path, card_name: str) -> None:
        """Elimina le immagini di una carta: quella semplice e le varianti numerate.

        Quando una riga scritta da un import precedente viene sostituita, le sue
        immagini vanno tolte dalla cache: col vecchio nome resterebbero orfane e,
        se il nome mostrato e' cambiato, Forge le userebbe per una carta fantasma.
        """
        prefix = forge_filename(card_name)
        if not pics_target.is_dir():
            return
        pattern = re.compile(re.escape(prefix) + r"\d*\.fullborder\.[a-z0-9]+$", re.IGNORECASE)
        for path in pics_target.iterdir():
            if path.is_file() and pattern.match(path.name):
                try:
                    path.unlink()
                except OSError:
                    pass

    def _ensure_numbered(self, pics_target: Path, card_name: str) -> None:
        """Passa da Nome.fullborder.ext a Nome1.fullborder.ext quando si aggiunge una seconda arte."""
        card_name = forge_filename(card_name)
        for extension in (".jpg", ".png"):
            unnumbered = pics_target / f"{card_name}.fullborder{extension}"
            numbered = pics_target / f"{card_name}1.fullborder{extension}"
            if unnumbered.is_file() and not numbered.exists():
                unnumbered.rename(numbered)

    def _place_image(
        self,
        item: ImportItem,
        pics_target: Path,
        art_index: int,
        art_total: int,
        options: ImportOptions,
        report: ImportReport,
        name: str | None = None,
    ) -> Path:
        """Scrive l'immagine in Cache/pics/cards col nome file di Forge.

        ``name`` permette di scrivere il retro di una carta multi-faccia col
        nome ufficiale della faccia posteriore invece che col nome mostrato.
        """
        source = item.image_path
        kept_alpha = _has_alpha(source)
        extension = ".png" if (kept_alpha and not options.crop) else ".jpg"
        destination = pics_target / image_file_name(
            (name or item.new_name).strip(), art_index, art_total, extension
        )

        if source.resolve() == destination.resolve():
            report.images_written += 1
            return destination

        pics_target.mkdir(parents=True, exist_ok=True)
        if options.crop:
            _write_cropped(source, destination, options.width, options.height)
        elif source.suffix.lower() in {".jpg", ".jpeg", ".png"} and not kept_alpha:
            shutil.copyfile(source, destination)
        else:
            _write_converted(source, destination)
        report.images_written += 1

        if options.move_within_pics and source.parent.resolve() == pics_target.resolve():
            try:
                source.unlink()
            except OSError:
                pass
        return destination

    # ---------- token ----------

    def _place_tokens(
        self,
        items: list[ImportItem],
        edition: Edition,
        code: str,
        options: ImportOptions,
        report: ImportReport,
        copy_mechanics: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        """Scrive i token custom e restituisce {script base: script nuovo}."""
        mapping: dict[str, str] = {}
        if not items:
            return mapping
        copy_mechanics = copy_mechanics or {}
        pics_target = self.token_pics_dir / code

        # Stem effettivo di ogni token. Se l'edizione ha gia' un token con lo
        # stesso nome si riusa il suo script, cosi' una nuova arte diventa una
        # variante del token che le carte richiamano gia' anche quando la base
        # riconosciuta per l'immagine e' diversa. Dentro lo stesso lotto i token
        # omonimi condividono lo stem anche se le basi rilevate non coincidono.
        stems: dict[int, str] = {}
        by_name: dict[str, str] = {}
        totals: dict[str, int] = {}
        for index, item in enumerate(items):
            name = item.new_name.strip()
            if not name or item.is_copy or not item.base:
                continue
            if item.copy_prefix or name.lower() in copy_mechanics:
                continue
            key = name.lower()
            filestem = by_name.get(key)
            if filestem is None:
                filestem = self._existing_token_stem(edition, name) or token_filestem(
                    item.base.entry, name
                )
                by_name[key] = filestem
            stems[index] = filestem
            totals[filestem.lower()] = totals.get(filestem.lower(), 0) + 1

        # Token-copia (Eternalize/Embalm): piu' arti della stessa copia
        # diventano righe [other] con collector propri, una per arte.
        copy_of: dict[int, tuple[str, str]] = {}
        copy_totals: dict[str, int] = {}
        for index, item in enumerate(items):
            name = item.new_name.strip()
            if not name:
                continue
            copy: tuple[str, str] | None = None
            if item.is_copy and item.copy_prefix:
                copy = (item.copy_prefix, item.copy_card or name)
            if copy is None:
                copy = copy_mechanics.get(name.lower())
            if copy is None:
                continue
            copy_of[index] = copy
            stem = f"{copy[0]}_{forge_image_slug(copy[1])}"
            copy_totals[stem] = copy_totals.get(stem, 0) + 1

        art_seen: dict[str, int] = {}

        for index, item in enumerate(items):
            name = item.new_name.strip()
            if not name:
                report.skipped += 1
                report.log(t("gen.skipped_token_name", name=item.image_path.name))
                continue
            copy = copy_of.get(index)
            if copy is not None:
                filestem = f"{copy[0]}_{forge_image_slug(copy[1])}"
                art_total = copy_totals.get(filestem, 1)
                collector: int | None = None
                art_index = 0
                if art_total > 1:
                    # Piu' art dello stesso token-copia: ognuna diventa una
                    # variante con una riga [other] e un collector propri.
                    art_seen[filestem] = art_seen.get(filestem, 0) + 1
                    art_index = art_seen[filestem]
                    if art_index == 1:
                        # Nuovo lotto di art: le righe e le immagini di un
                        # import precedente vengono sostituite.
                        edition.remove_other(filestem)
                        self._remove_token_variants(pics_target, filestem)
                    collector = edition.next_other_collector()
                    edition.add_other(filestem, collector, item.artist)
                self._place_copy_image(
                    item,
                    edition,
                    pics_target,
                    copy,
                    options,
                    report,
                    collector=collector,
                    art_index=art_index,
                    art_total=art_total,
                )
                continue
            if not item.base:
                report.skipped += 1
                report.log(t("gen.skipped_token_base", name=item.image_path.name))
                continue

            base_stem = Path(item.base.entry).stem
            filestem = stems.get(index) or token_filestem(item.base.entry, name)
            if base_stem.lower() in mapping:
                report.log(
                    t("gen.token_multi", stem=base_stem, filestem=mapping[base_stem.lower()])
                )
            else:
                mapping[base_stem.lower()] = filestem

            key = filestem.lower()
            art_total = totals.get(key, 1)
            if art_total > 1:
                # Piu' art dello stesso token: ognuna diventa una variante, con
                # una riga e un collector propri, cosi' Forge ne mostra una a caso.
                art_seen[key] = art_seen.get(key, 0) + 1
                art_index = art_seen[key]
                if art_index == 1:
                    # Nuovo lotto di art per questo token: le righe e le immagini
                    # di un import precedente vengono sostituite, altrimenti ad
                    # ogni re-importazione se ne accumulerebbero di nuove.
                    edition.remove_tokens(filestem)
                    self._remove_token_variants(pics_target, filestem)
                collector = edition.next_token_collector()
                edition.add_token(filestem, collector, item.artist)
                item.notes.append(
                    t("gen.token_variant", base=item.base.name, index=art_index, total=art_total)
                )
            elif edition.token_count(filestem):
                collector = _token_collector_of(edition, filestem)
            else:
                collector = edition.next_token_collector()
                edition.add_token(filestem, collector, item.artist)
                item.notes.append(t("gen.token_created", base=item.base.name))

            item.image_dest = self._place_token_image(
                item, pics_target, collector, filestem, options, report
            )
            item.script_dest = self._write_token_script(item, filestem, report)
            report.tokens += 1
            report.log(t("gen.token_line", name=name, filestem=filestem, collector=collector))
        return mapping

    def _existing_token_stem(self, edition: Edition, name: str) -> str | None:
        """Stem di un token gia' nell'edizione il cui script si chiama `name`.

        Il nome viene letto dagli script in custom/tokens, cosi' il token viene
        ritrovato anche se la base riconosciuta per la nuova arte e' diversa:
        senza questo controllo la stessa immagine reimportata finirebbe su uno
        stem nuovo (token distinto) invece che fra le varianti di quello che le
        carte del set gia' richiamano.
        """
        target = name.strip().lower()
        if not target:
            return None
        for line in edition.token_lines:
            stem = _token_line_stem(line)
            if stem and _script_name(self.tokens_dir / f"{stem}.txt").strip().lower() == target:
                return stem
        return None

    def _copy_mechanics(self, edition: Edition, cards_dir: Path) -> dict[str, tuple[str, str]]:
        """{nome carta (lower): (prefisso, nome)} per i token-copia del set."""
        return copy_mechanics_in(cards_dir, edition.names())

    def _place_copy_image(
        self,
        item: ImportItem,
        edition: Edition,
        pics_target: Path,
        copy: tuple[str, str],
        options: ImportOptions,
        report: ImportReport,
        collector: int | None = None,
        art_index: int = 0,
        art_total: int = 0,
    ) -> None:
        """Registra l'immagine di un token-copia (Eternalize/Embalm).

        Questi token non hanno uno script: Forge crea una copia della carta e
        la disegna con la image key "eternalize_<nome>"/"embalm_<nome>", che si
        risolve nelle righe della sezione [other] dell'edizione.

        Piu' arti dello stesso token-copia ricevono ognuna un collector proprio
        (righe [other] omonime): Forge ne sceglie una a caso, come per i token.
        """
        prefix, card_name = copy
        filestem = f"{prefix}_{forge_image_slug(card_name)}"
        if collector is None:
            if edition.other_count(filestem):
                collector = _other_collector_of(edition, filestem)
            else:
                collector = edition.next_other_collector()
                edition.add_other(filestem, collector, item.artist)
        item.image_dest = self._place_token_image(
            item, pics_target, collector, filestem, options, report
        )
        if art_total > 1:
            item.notes.append(
                t(
                    "gen.copy_token_variant",
                    prefix=prefix,
                    card=card_name,
                    index=art_index,
                    total=art_total,
                )
            )
        else:
            item.notes.append(t("gen.copy_token", prefix=prefix, card=card_name))
        report.tokens += 1
        report.log(t("gen.copy_token_line", prefix=prefix, card=card_name, collector=collector))

    def _place_emblems(
        self,
        items: list[ImportItem],
        edition: Edition,
        code: str,
        options: ImportOptions,
        report: ImportReport,
    ) -> None:
        """Registra le immagini degli emblemi dei Planeswalker del set.

        Un emblema non ha uno script: Forge copia l'abilita' del Planeswalker e
        lo disegna con la chiave "emblem_<slug>", che risolve nella sezione
        [other] dell'edizione della carta che lo ha creato (il Planeswalker del
        set). Il tool copia quindi solo l'immagine e registra la riga, come per
        i token-copia: la chiave e' quella del nome ufficiale della carta base,
        perche' il re-skin condivide il suo script.
        """
        if not items:
            return
        pics_target = self.token_pics_dir / code
        for item in items:
            name = item.new_name.strip()
            if not name:
                report.skipped += 1
                report.log(t("gen.skipped_token_name", name=item.image_path.name))
                continue
            if not item.base:
                report.skipped += 1
                report.log(t("gen.skipped_emblem_base", name=item.image_path.name))
                continue
            try:
                base_script = self.db.script_text(item.base)
            except (KeyError, OSError):
                base_script = ""
            key = emblem_image_key(item.base.name.strip(), base_script)
            if edition.other_count(key):
                collector = _other_collector_of(edition, key)
            else:
                collector = edition.next_other_collector()
                edition.add_other(key, collector, item.artist)
            item.image_dest = self._place_token_image(
                item, pics_target, collector, key, options, report
            )
            item.notes.append(t("gen.emblem", card=item.base.name))
            report.emblems += 1
            report.log(t("gen.emblem_line", card=item.base.name, collector=collector))

    def _place_token_image(
        self,
        item: ImportItem,
        pics_target: Path,
        collector: int,
        filestem: str,
        options: ImportOptions,
        report: ImportReport,
    ) -> Path:
        source = item.image_path
        kept_alpha = _has_alpha(source)
        extension = ".png" if (kept_alpha and not options.crop) else ".jpg"
        destination = pics_target / f"{collector}_{filestem}{extension}"

        if source.resolve() == destination.resolve():
            report.images_written += 1
            return destination

        pics_target.mkdir(parents=True, exist_ok=True)
        if options.crop:
            _write_cropped(source, destination, options.width, options.height)
        elif source.suffix.lower() in {".jpg", ".jpeg", ".png"} and not kept_alpha:
            shutil.copyfile(source, destination)
        else:
            _write_converted(source, destination)
        report.images_written += 1
        return destination

    def _remove_token_variants(self, pics_target: Path, filestem: str) -> None:
        """Elimina le immagini <collector>_<stem>.<ext> di un token.

        Quando il token viene reimportato con un nuovo lotto di art le righe
        [tokens] vengono riscritte con collector nuovi: senza questa pulizia le
        immagini dei collector precedenti resterebbero orfane nella cache.
        """
        if not pics_target.is_dir():
            return
        pattern = re.compile(
            r"^\d+_" + re.escape(filestem) + r"\.[a-z0-9]+$", re.IGNORECASE
        )
        for path in pics_target.iterdir():
            if path.is_file() and pattern.match(path.name):
                try:
                    path.unlink()
                except OSError:
                    pass

    def _write_token_script(
        self, item: ImportItem, filestem: str, report: ImportReport
    ) -> Path | None:
        destination = self.tokens_dir / f"{filestem}.txt"
        try:
            base_script = self.db.script_text(item.base)
        except (KeyError, OSError) as exc:
            report.log(t("gen.warn_token_script", name=item.new_name, error=exc))
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            build_token_script(base_script, item.new_name.strip()), encoding="utf-8"
        )
        report.scripts_written += 1
        return destination

    def _rewire_token_refs(
        self,
        edition: Edition,
        cards_dir: Path,
        mapping: dict[str, str],
        report: ImportReport,
    ) -> None:
        """Fa puntare ai token importati le carte del set che li creano.

        Nel testo di una carta un token si crea con
        "DB$ Token | TokenScript$ <script>": se lo script richiamato e' un token
        base di cui e' stata importata una stampa custom, la carta deve puntare
        alla nuova stampa, altrimenti in partita compare il token originale.
        Si aggiornano gli script custom del set e, per le carte che ne sono
        prive (re-skin come carte ufficiali ristampate con arte propria), se ne
        crea uno copiando le regole della carta base. Uno script viene scritto
        solo se la carta richiama davvero un token importato, cosi' le carte
        senza token restano intatte.
        """
        if not mapping:
            return
        existing = _card_scripts(cards_dir)
        for entry in edition.entries:
            base_name = entry.name.strip()
            if not base_name:
                continue
            path = existing.get(base_name.lower())
            if path is not None:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
            else:
                # La carta non ha uno script nel set: si prendono le regole
                # della carta base, che richiamano ancora i token base.
                base = self.db.by_name(base_name)
                if base is None:
                    continue
                try:
                    text = self.db.script_text(base)
                except (KeyError, OSError) as exc:
                    report.log(t("gen.warn_token_refs", file=base_name, error=exc))
                    continue
                path = _card_script_path(cards_dir, base_name)
            updated = _replace_token_refs(text, mapping)
            if updated == text:
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(updated, encoding="utf-8")
            except OSError as exc:
                report.log(t("gen.warn_token_refs", file=path.name, error=exc))
                continue
            existing[base_name.lower()] = path
            report.log(t("gen.token_refs_updated", file=path.name))


def _has_alpha(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            return image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
    except OSError:
        return False


_CARD_W_MM = 63.0
_CARD_H_MM = 88.0


def _card_crop_box(width: int, height: int, target_ratio: float) -> tuple[int, int, int, int]:
    """Riquadro che rimuove il bleed edge e riporta l'immagine a 63x88.

    Le immagini custom hanno spesso un "bleed edge" (margine uniforme oltre il
    bordo della carta) per il taglio fisico, quindi sono piu' grandi dello
    standard in entrambe le direzioni. Poiche' la carta standard e' 63x88 mm,
    la differenza tra altezza e larghezza resta sempre 88 - 63 = 25 mm anche
    col bleed: il rapporto (height - width) / 25 da' i pixel per mm, da cui si
    ricava la dimensione reale della carta e si taglia via il bleed (centrato).
    Se il calcolo non e' valido (immagine non conforme) si ripiega sul semplice
    taglio dell'eccedenza per rispettare il rapporto 63:88.
    """
    if height > width:
        scale = (height - width) / (_CARD_H_MM - _CARD_W_MM)
        card_w = _CARD_W_MM * scale
        card_h = _CARD_H_MM * scale
        if 0 < card_w <= width and 0 < card_h <= height:
            left = round((width - card_w) / 2)
            top = round((height - card_h) / 2)
            return (left, top, left + round(card_w), top + round(card_h))
    if width / height > target_ratio:
        crop_width = max(1, round(height * target_ratio))
        left = (width - crop_width) // 2
        return (left, 0, left + crop_width, height)
    crop_height = max(1, round(width / target_ratio))
    top = (height - crop_height) // 2
    return (0, top, width, top + crop_height)


def _write_cropped(source: Path, destination: Path, width: int, height: int) -> None:
    """Rimuove il bleed edge e porta l'immagine allo standard 63x88 (width x height).

    Le carte custom sono piu' grandi dello standard per il bleed edge: stirarle
    a 488x680 le deforma. Qui si taglia il margine in eccesso (calcolato dal
    rapporto tra le dimensioni reali e lo standard 63x88) e solo dopo si scala,
    cosi' l'immagine raggiunge la dimensione standard senza deformazioni.
    """
    with Image.open(source) as image:
        mode = "RGBA" if _has_alpha(source) and destination.suffix == ".png" else "RGB"
        converted = image.convert(mode)
        box = _card_crop_box(converted.width, converted.height, width / height)
        converted = converted.crop(box).resize((width, height), Image.LANCZOS)
        converted.save(destination)


def _write_converted(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        if destination.suffix == ".png":
            image.convert("RGBA").save(destination)
        else:
            image.convert("RGB").save(destination, quality=95)


def is_card_image(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTENSIONS


def scan_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and is_card_image(p))


def collapse_extensions(folder: Path) -> None:
    """Riporta al formato canonico i file con doppia estensione.

    Versioni precedenti del tool potevano salvare "Nome.fullborder.jpg.png";
    Forge prova solo "<nome>.jpg" e "<nome>.png", quindi quei file non
    venivano mai trovati e l'arte risultava mancante (non compariva fra le
    varianti della carta). Qui il nome tiene solo l'ultima estensione, che e'
    quella reale del file.
    """
    if not folder.is_dir():
        return
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        inner = Path(path.stem)
        if inner.suffix.lower() not in _IMAGE_EXTENSIONS:
            continue
        target = path.with_name(inner.stem + path.suffix)
        if target == path or target.exists():
            continue
        try:
            path.rename(target)
        except OSError:
            continue
