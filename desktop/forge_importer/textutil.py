"""Normalizzazione del testo per il confronto (nomi carte e testo Oracle)."""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = {"\u2019", "\u2018", "\u02bc", "`", "\u00b4"}
_DASHES = {"\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"}
_PUNCT_RE = re.compile(r"[^\w\s/+-]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_COMMA_RE = re.compile(r",(?=[^\W\d_])", re.UNICODE)
_LIGATURE = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
# Rumore OCR: ideogrammi e simboli CJK non appartengono ai nomi delle carte.
_CJK_RE = re.compile(
    r"[\u2e80-\u303f\u3040-\u30ff\u3100-\u312f\u31a0-\u31bf"
    r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]",
    re.UNICODE,
)
# Lettere dei simboli di mana (bianco/blu/nero/rosso/verde/incolore/X/neve).
_MANA_LETTERS = "WUBRGCXS"
# L'OCR confonde i simboli di mana con lettere/cifre simili (U->O/0, 1->I/l,
# 2->Z, 3->E, 5->S, 6->G, 8->B): le accettiamo quando compongono un costo.
_COST_CHARS = _MANA_LETTERS + "OIZE"
# Token di costo di mana: inizia con una cifra ("2", "20", "2G", "5O0").
_COST_TOKEN_RE = re.compile(rf"^\d[\d{_COST_CHARS}]*$", re.IGNORECASE)
# Costo attaccato all'ultima parola senza spazio ("Cohoot2", "Wyvern5O0").
_GLUED_COST_RE = re.compile(rf"^(.*?[^\W\d_])(\d[\d{_COST_CHARS}]*)$", re.IGNORECASE)
_BRACES_RE = re.compile(r"[{}]")


def _basic_clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for ligature, replacement in _LIGATURE.items():
        text = text.replace(ligature, replacement)
    for char in _APOSTROPHES:
        text = text.replace(char, "'")
    for char in _DASHES:
        text = text.replace(char, "-")
    text = text.replace("\\n", " ").replace("\n", " ")
    return text


def normalize_plain(text: str) -> str:
    """Chiave di confronto per i nomi delle carte."""
    return _SPACE_RE.sub(" ", _basic_clean(text).strip()).lower()


def normalize_for_compare(text: str) -> str:
    """Testo Oracle ridotto a parole e numeri, utile per il confronto fuzzy."""
    text = _basic_clean(text).lower()
    text = text.replace("|", "l")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def normalize_ocr(text: str) -> str:
    """Correzioni tipiche degli errori OCR sulle carte."""
    text = _basic_clean(text)
    text = re.sub(r"(?<![A-Za-z])[lI|](?![A-Za-z])", "1", text)  # "l" isolato -> "1"
    text = text.replace("\u00a0", " ")
    return text


def has_letters(text: str) -> bool:
    """Vero se il testo contiene almeno una lettera (non solo cifre/simboli)."""
    return _LETTER_RE.search(text) is not None


def clean_title(text: str) -> str:
    """Ripulisce il titolo letto dall'OCR.

    Sulle carte il costo di mana sta a destra del titolo e l'OCR tende a
    unirlo al nome in vari modi: come token separato ("Cohoot 2"), attaccato
    all'ultima parola ("Cohoot2", "Dragon80") o come numero seguito dalle
    lettere dei simboli di mana ("Cohoot 2G", "{2}{G}"). Vengono rimossi i
    token finali privi di lettere (numeri e simboli), quelli di puro costo di
    mana e le cifre attaccate all'ultima parola. Si elimina anche il rumore
    OCR composto da ideogrammi/simboli CJK, che non appartengono ai nomi.
    Viene inoltre reinserito lo spazio dopo la virgola quando l'OCR lo perde.
    """
    text = _SPACE_RE.sub(" ", _basic_clean(text).strip())
    text = _CJK_RE.sub(" ", text)
    text = _BRACES_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip()
    text = _COMMA_RE.sub(", ", text)
    tokens = text.split(" ")
    while tokens and (not has_letters(tokens[-1]) or _COST_TOKEN_RE.match(tokens[-1])):
        tokens.pop()
    if tokens:
        glued = _GLUED_COST_RE.match(tokens[-1])
        if glued:
            tokens[-1] = glued.group(1)
    return " ".join(tokens).strip()
