"""Rarita' delle carte dedotta dalle edizioni ufficiali di Forge.

Forge non memorizza la rarita' nei card script: vive solo nelle edizioni
(res/editions/*.txt) nel formato "CollectorNumber Rarity Name @Artist".
Quando una carta compare in piu' edizioni si preferisce la prima stampa,
cioe' quella con la data piu' antica; in mancanza di date si usa comunque
l'ultima lettura utile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .textutil import normalize_plain

_ENTRY_RE = re.compile(r"^\s*\d*\u2605*\s+([LCURMSlcurms])\s+(.+?)\s*(@.*)?$")
_SET_REF_RE = re.compile(r"\|[A-Za-z0-9]+$")
_DATE_RE = re.compile(r"^\s*Date\s*=\s*(.+?)\s*$")


@dataclass(frozen=True)
class _Printing:
    rarity: str
    date: str


class RarityIndex:
    """Mappa nome carta -> rarita' della stampa piu' antica conosciuta."""

    def __init__(self, printings: dict[str, _Printing]):
        self._printings = printings

    @classmethod
    def load(cls, editions_dir: Path) -> "RarityIndex":
        printings: dict[str, _Printing] = {}
        if not editions_dir.is_dir():
            return cls(printings)
        for file in sorted(editions_dir.glob("*.txt")):
            date = ""
            section = ""
            for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    section = stripped[1:-1].strip().lower()
                    continue
                if section == "metadata":
                    match = _DATE_RE.match(line)
                    if match:
                        date = match.group(1)
                elif section == "cards" and stripped:
                    entry = _ENTRY_RE.match(stripped)
                    if not entry:
                        continue
                    rarity = entry.group(1).upper()
                    name = _SET_REF_RE.sub("", entry.group(2)).strip()
                    key = normalize_plain(name)
                    current = printings.get(key)
                    if current is None or _is_earlier(date, current.date):
                        printings[key] = _Printing(rarity, date)
        return cls(printings)

    def lookup(self, name: str) -> str:
        """Rarita' dedotta per una carta, oppure stringa vuota se sconosciuta."""
        printing = self._printings.get(normalize_plain(name))
        return printing.rarity if printing else ""


def _is_earlier(candidate: str, current: str) -> bool:
    if not candidate:
        return False
    return not current or candidate < current
