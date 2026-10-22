"""Regole di denominazione delle carte, indipendenti dall'interfaccia grafica.

Qui vivono le poche regole che non dipendono dalla GUI: come ricavare il nome
dal file, come riconoscere una terra base e come scrivere il nome di un token.
"""

from __future__ import annotations

import re
from pathlib import Path

from .carddb import CardInfo

DEFAULT_RARITY = "C"
BASIC_LANDS = ("Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes")
_WORD_SPLIT_RE = re.compile(r"[\s,/\\|._-]+")


def name_from_filename(path: Path) -> str:
    """Nome alternativo ricavato dal file, usato se l'OCR non legge il titolo.

    I proxy sono spesso nominati "NomeBase (Nuovo Nome)[ (n)].png": in quel
    caso il nuovo nome e' quello tra parentesi, altrimenti si usa il nome file.
    """
    stem = re.sub(r"\s*\(\d+\)\s*$", "", path.stem).strip()
    match = re.search(r"^(.*?)\s*\((.*)\)\s*$", stem)
    if match and match.group(2).strip():
        return match.group(2).strip()
    return stem or path.stem


def detect_basic_land(text: str) -> str:
    """Nome della terra base se il testo comincia con essa, altrimenti ''.

    Le terre base in arte completa non hanno testo delle regole e l'OCR non
    legge il titolo: il nome resta solo nel nome del file ("Forest A.png").
    Si controlla solo la prima parola per non scambiare per terra base carte
    come "Karplusan Forest" o "Yama Tsukami, Floating Mountain".
    """
    if not text:
        return ""
    tokens = _WORD_SPLIT_RE.split(text.strip())
    head = next((t for t in tokens if t), "")
    for land in BASIC_LANDS:
        if head.lower() == land.lower():
            return land
    return ""


def is_basic_land(card: CardInfo | None) -> bool:
    """Vero se la carta e' una terra base (Plains, Island, Swamp, ...)."""
    if card is None:
        return False
    return card.name.strip().lower() in {n.lower() for n in BASIC_LANDS}


def token_name(text: str) -> str:
    """Nome di un token letto dall'OCR, con le maiuscole riportate al normale.

    Sulle carte token il nome e' stampato tutto in maiuscolo ("BALAHARA"):
    viene convertito in "Balahara" per non lasciare il nome urlato in Forge.
    """
    text = text.strip()
    return text.title() if text.isupper() else text
