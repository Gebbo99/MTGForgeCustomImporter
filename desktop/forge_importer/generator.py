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
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import date as date_cls
from pathlib import Path

from PIL import Image

from .carddb import CardDB, CardInfo
from .i18n import t

RARITIES = ("L", "C", "U", "R", "M", "S")
_ENTRY_RE = re.compile(r"^\s*(\d*)(\u2605*)\s+([LCURMSlcurms])\s+(.+?)\s*(@.*)?$")
_ARTIST_RE = re.compile(r"@\s*(.+)$")
# Suffisso extraParams delle varianti: " ${"flavorName": "NomeMostrato"}"
_FLAVOR_RE = re.compile(r"\s*\$\{(.*)\}\s*$")
_FLAVOR_NAME_RE = re.compile(r'"flavorName"\s*:\s*"([^"]*)"', re.IGNORECASE)
_TOKEN_LINE_RE = re.compile(r"^\s*(\d+)\s+([^\s@]+)")
_TOKEN_REF_RE = re.compile(r"(TokenScript\$\s*)([^\s|]+)")
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
            lines.extend(self.token_lines)
        for name, section_lines in self.other_sections:
            lines.append("")
            lines.append(f"[{name}]")
            lines.extend(section_lines)
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
    flavor_match = _FLAVOR_RE.search(text)
    if flavor_match:
        name_match = _FLAVOR_NAME_RE.search(flavor_match.group(1))
        if name_match:
            flavor_name = name_match.group(1)
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
        raw=line,
    )


def _format_entry(entry: EditionEntry) -> str:
    prefix = entry.collector + "\u2605" * entry.stars
    text = f"{prefix} {entry.rarity} {entry.name}".strip()
    if entry.artist:
        text += f" @{entry.artist}"
    if entry.flavor_name:
        text += f' ${{"flavorName": "{entry.flavor_name}"}}'
    return text


def _token_line_stem(line: str) -> str:
    """Nome dello script (filestem) da una riga della sezione [tokens]."""
    match = _TOKEN_LINE_RE.match(line)
    return match.group(2) if match else ""


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


def image_file_name(card_name: str, art_index: int, art_total: int, extension: str) -> str:
    number = "" if art_total <= 1 else str(art_index)
    return f"{forge_filename(card_name)}{number}.fullborder{extension}"


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

        code = edition.code.strip() or edition_code
        pics_target = self.pics_dir / code
        cards_dir = self.custom_dir / "cards"
        pics_target.mkdir(parents=True, exist_ok=True)
        collapse_extensions(pics_target)
        collapse_extensions(self.token_pics_dir / code)

        card_items = [item for item in items if not item.is_token]
        token_items = [item for item in items if item.is_token]

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
            base_name = item.base.name.strip()
            # Re-skin: la riga usa le regole della carta base e il nome nuovo come
            # flavorName, cosi' Forge mostra la nuova arte fra le varianti della
            # carta base invece che come carta a se' stante.
            flavor_name = "" if name.lower() == base_name.lower() else name

            if art_total == 1:
                # Una sola immagine con questo nome: re-import idempotente. Se la
                # carta esiste gia' la riga viene aggiornata e l'immagine riusata,
                # senza accumulare copie duplicate ad ogni ri-importazione.
                existing = edition.find_cards(name)
                collector = (
                    int(existing[0].collector)
                    if existing and existing[0].collector.isdigit()
                    else edition.next_collector()
                )
                for entry in existing:
                    edition.remove_card(entry)
                self._remove_numbered_variants(pics_target, name)
                item.image_dest = self._place_image(
                    item, pics_target, 1, 1, options, report
                )
                edition.add_card(
                    base_name, item.rarity, collector, 0, item.artist, flavor_name=flavor_name
                )
                if flavor_name:
                    item.notes.append(t("gen.variant_of", base=base_name, name=name))
                    if self.db.by_name(name) is not None:
                        item.notes.append(t("gen.name_official"))
                else:
                    item.notes.append(t("gen.same_rules"))
            else:
                # Piu' immagini con lo stesso nome importate insieme: ognuna
                # diventa una variante (arte) della stessa carta.
                if art_seen[key] == 1:
                    self._ensure_numbered(pics_target, name)
                    for entry in edition.find_cards(name):
                        edition.remove_card(entry)
                collector = edition.next_collector()
                item.image_dest = self._place_image(
                    item, pics_target, art_index, art_total, options, report
                )
                edition.add_card(
                    base_name,
                    item.rarity,
                    collector,
                    item.stars,
                    item.artist,
                    flavor_name=flavor_name,
                )
                if flavor_name:
                    item.notes.append(
                        t("gen.variant_of_art", base=base_name, name=name, index=art_index, total=art_total)
                    )
                else:
                    item.notes.append(t("gen.same_rules"))
            report.imported += 1

        copy_mechanics = self._copy_mechanics(edition, cards_dir)
        token_refs = self._place_tokens(
            token_items, edition, code, options, report, copy_mechanics
        )
        self._rewire_token_refs(edition, cards_dir, token_refs, report)

        edition.save()
        report.log(t("gen.edition_updated", path=edition.path))
        return report

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
    ) -> Path:
        source = item.image_path
        kept_alpha = _has_alpha(source)
        extension = ".png" if (kept_alpha and not options.crop) else ".jpg"
        destination = pics_target / image_file_name(item.new_name.strip(), art_index, art_total, extension)

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
        for item in items:
            name = item.new_name.strip()
            if not name:
                report.skipped += 1
                report.log(t("gen.skipped_token_name", name=item.image_path.name))
                continue
            copy: tuple[str, str] | None = None
            if item.is_copy and item.copy_prefix:
                copy = (item.copy_prefix, item.copy_card or name)
            if copy is None:
                copy = copy_mechanics.get(name.lower())
            if copy is not None:
                self._place_copy_image(item, edition, pics_target, copy, options, report)
                continue
            if not item.base:
                report.skipped += 1
                report.log(t("gen.skipped_token_base", name=item.image_path.name))
                continue

            base_stem = Path(item.base.entry).stem
            filestem = token_filestem(item.base.entry, name)
            if base_stem.lower() in mapping:
                report.log(
                    t("gen.token_multi", stem=base_stem, filestem=mapping[base_stem.lower()])
                )
            else:
                mapping[base_stem.lower()] = filestem

            if edition.token_count(filestem):
                collector = _token_collector_of(edition, filestem)
            else:
                collector = edition.next_token_collector()
                edition.add_token(filestem, collector, item.artist)

            item.image_dest = self._place_token_image(
                item, pics_target, collector, filestem, options, report
            )
            item.script_dest = self._write_token_script(item, filestem, report)
            item.notes.append(t("gen.token_created", base=item.base.name))
            report.tokens += 1
            report.log(t("gen.token_line", name=name, filestem=filestem, collector=collector))
        return mapping

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
    ) -> None:
        """Registra l'immagine di un token-copia (Eternalize/Embalm).

        Questi token non hanno uno script: Forge crea una copia della carta e
        la disegna con la image key "eternalize_<nome>"/"embalm_<nome>", che si
        risolve nelle righe della sezione [other] dell'edizione.
        """
        prefix, card_name = copy
        filestem = f"{prefix}_{forge_image_slug(card_name)}"
        if edition.other_count(filestem):
            collector = _other_collector_of(edition, filestem)
        else:
            collector = edition.next_other_collector()
            edition.add_other(filestem, collector, item.artist)
        item.image_dest = self._place_token_image(
            item, pics_target, collector, filestem, options, report
        )
        item.notes.append(t("gen.copy_token", prefix=prefix, card=card_name))
        report.tokens += 1
        report.log(t("gen.copy_token_line", prefix=prefix, card=card_name, collector=collector))

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
        """Fa puntare le carte del set ai token appena importati.

        Nel testo delle regole una carta crea un token con
        "DB$ Token | TokenScript$ <script>": le carte custom del set che
        richiamano uno dei token base importati vengono riscritte per usare la
        nuova stampa, cosi' il re-skin compare in partita.
        """
        if not mapping or not cards_dir.is_dir():
            return
        names = edition.names()
        for path in sorted(cards_dir.glob("**/*.txt")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if script_name(text).strip().lower() not in names:
                continue
            updated = _replace_token_refs(text, mapping)
            if updated == text:
                continue
            try:
                path.write_text(updated, encoding="utf-8")
            except OSError as exc:
                report.log(t("gen.warn_token_refs", file=path.name, error=exc))
                continue
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
