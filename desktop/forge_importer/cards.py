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
# Le carte multi-faccia numerate portano davanti "N_M_" (carta N, faccia M).
_INDEX_PREFIX_RE = re.compile(r"^\d+_\d+_|^\d+_(?=[A-Za-z])")
_REAL_NAME_RE = re.compile(r"^(.*?)\s*\(")
_CUSTOM_NAME_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*\d*\s*$")
_NAME_KEY_RE = re.compile(r"[^0-9a-z]+")


def custom_name_from_filename(path: Path) -> str:
    """Nome custom scritto fra parentesi nel nome file.

    I proxy seguono la convenzione "<NomeReale> (<NomeCustom>) [n].ext": qui si
    isola la parte fra parentesi, che per una faccia e' il nome mostrato. E'
    l'utente a scriverla, quindi e' piu' affidabile del titolo letto dall'OCR
    (che su una singola immagine puo' perdere uno spazio).
    """
    stem = re.sub(r"\s*\(\d+\)\s*$", "", path.stem).strip()
    match = _CUSTOM_NAME_RE.search(stem)
    if match and match.group(2).strip():
        return match.group(2).strip()
    return ""


def same_name_ignoring_spaces(first: str, second: str) -> bool:
    """Vero se i due nomi coincidono a meno di spazi e punteggiatura."""
    first_key = _NAME_KEY_RE.sub("", first.lower())
    return bool(first_key) and first_key == _NAME_KEY_RE.sub("", second.lower())


def name_from_filename(path: Path) -> str:
    """Nome alternativo ricavato dal file, usato se l'OCR non legge il titolo.

    I proxy sono spesso nominati "NomeBase (Nuovo Nome)[ (n)].png": in quel
    caso il nuovo nome e' quello tra parentesi, altrimenti si usa il nome file.
    """
    stem = re.sub(r"\s*\(\d+\)\s*$", "", path.stem).strip()
    return custom_name_from_filename(path) or stem or path.stem


def real_name_from_filename(path: Path) -> str:
    """Nome reale della carta ricavato dal file (parte prima delle parentesi).

    I proxy seguono la convenzione "<NomeReale> (<NomeCustom>) [n].ext" e le
    carte multi-faccia anche "N_M_<NomeReale> (<NomeCustom>).ext": qui si isola
    la parte prima delle parentesi, che per le facce e' il nome ufficiale.
    Serve a collegare le due immagini (fronte e retro) della stessa carta
    multi-faccia, che l'utente fornisce come file separati.
    """
    stem = re.sub(r"\s*\(\d+\)\s*$", "", path.stem).strip()
    stem = _INDEX_PREFIX_RE.sub("", stem).strip()
    match = _REAL_NAME_RE.search(stem)
    return (match.group(1).strip() if match else stem) or path.stem


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
