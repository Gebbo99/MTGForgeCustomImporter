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

CACHE_VERSION = 3


@dataclass(frozen=True)
class CardInfo:
    name: str
    oracle: str
    types: str
    mana_cost: str
    pt: str
    entry: str
    source: str

    @property
    def oracle_norm(self) -> str:
        return normalize_for_compare(self.oracle)


def _parse_script(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if ":" in raw_line:
            key, _, value = raw_line.partition(":")
            key = key.strip()
        else:
            key, value = "", raw_line.strip()
        if key in {"Name", "Oracle", "Types", "ManaCost", "PT"}:
            fields[key] = value.strip()
            current_key = key
        elif current_key == "Oracle":
            fields["Oracle"] = (fields.get("Oracle", "") + " " + raw_line.strip()).strip()
        else:
            current_key = None
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
        # Archivio aperto una sola volta: script_text() legge uno script per
        # chiamata e riaprire il .zip ogni volta costa decine di millisecondi
        # (con le centinaia di carte di un set l'attesa congelava l'interfaccia).
        self._archive: zipfile.ZipFile | None = None
        for card in cards:
            key = normalize_plain(card.name)
            self._by_name.setdefault(key, card)

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
