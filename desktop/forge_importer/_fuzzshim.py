"""Sottoinsieme puro-Python di rapidfuzz, usato su Android.

Su desktop il riconoscimento usa `rapidfuzz` (estensione C++ veloce); su
Android quell'estensione non e' compilabile, quindi `matcher.py` ripiega su
questo modulo, che espone gli stessi nomi:

    fuzz.ratio, fuzz.partial_ratio, fuzz.token_sort_ratio,
    fuzz.token_set_ratio, fuzz.WRatio
    process.extract, process.extractOne

`process` usa un prefiltro a bigrammi: lo scorer completo viene calcolato solo
sui candidati piu' promettenti, cosi' la ricerca su ~30.000 nomi resta rapida
anche in Python puro.
"""

from __future__ import annotations

from difflib import SequenceMatcher

# Quanti candidati passano il prefiltro e finiscono nello scorer completo.
PREFILTER_POOL = 700


def _ratio(a: str, b: str) -> float:
    """Similarita' 0-100 (stessa definizione di fuzz.ratio di rapidfuzz)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio() * 100.0


def partial_ratio(a: str, b: str) -> float:
    """Miglior similarita' fra la stringa corta e una porzione della lunga."""
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    best = 0.0
    for block in SequenceMatcher(None, shorter, longer, autojunk=False).get_matching_blocks():
        start = max(0, block.b - block.a)
        window = longer[start:start + len(shorter)]
        score = SequenceMatcher(None, shorter, window, autojunk=False).ratio()
        if score > best:
            best = score
    return best * 100.0


def ratio(a: str, b: str) -> float:
    return _ratio(a, b)


def token_sort_ratio(a: str, b: str) -> float:
    return _ratio(" ".join(sorted(a.split())), " ".join(sorted(b.split())))


def token_set_ratio(a: str, b: str) -> float:
    tokens_a, tokens_b = set(a.split()), set(b.split())
    common = tokens_a & tokens_b
    if not common:
        return token_sort_ratio(a, b)
    shared = " ".join(sorted(common))
    only_a = " ".join(sorted(tokens_a - common))
    only_b = " ".join(sorted(tokens_b - common))
    joined_a = f"{shared} {only_a}".strip()
    joined_b = f"{shared} {only_b}".strip()
    return max(_ratio(shared, joined_a), _ratio(shared, joined_b), _ratio(joined_a, joined_b))


def WRatio(a: str, b: str) -> float:
    """Approssimazione di fuzz.WRatio: combina ratio, partial e token."""
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    best = _ratio(a, b)
    length_ratio = len(longer) / len(shorter)
    if length_ratio >= 1.5:
        best = max(best, partial_ratio(a, b) * (0.9 if length_ratio < 8 else 0.6))
    if min(len(a.split()), len(b.split())) > 1:
        best = max(best, token_sort_ratio(a, b), token_set_ratio(a, b) * 0.95)
    return min(best, 100.0)


# --------------------------------------------------------------------------
# process
# --------------------------------------------------------------------------

_bigram_cache: dict[int, tuple] = {}


def _bigrams(text: str) -> frozenset:
    if len(text) < 2:
        return frozenset(text)
    return frozenset(text[i : i + 2] for i in range(len(text) - 1))


def _cached_bigrams(choices) -> list:
    entry = _bigram_cache.get(id(choices))
    if entry is None or entry[0] is not choices:
        entry = (choices, [_bigrams(choice) for choice in choices])
        _bigram_cache[id(choices)] = entry
    return entry[1]


def extract(query: str, choices, scorer=WRatio, limit: int = 5) -> list[tuple]:
    """Come rapidfuzz.process.extract: [(scelta, punteggio, indice), ...]."""
    choices = list(choices)
    grams = _cached_bigrams(choices)
    query_grams = _bigrams(query)
    total = len(query_grams) or 1

    if len(choices) > PREFILTER_POOL:
        preliminary = sorted(
            ((len(query_grams & gram) / total, index) for index, gram in enumerate(grams)),
            key=lambda item: -item[0],
        )[:PREFILTER_POOL]
        indices = [index for _, index in preliminary]
    else:
        indices = range(len(choices))

    scored = [(choices[index], scorer(query, choices[index]), index) for index in indices]
    scored.sort(key=lambda item: (-item[1], item[2]))
    return scored[:limit]


def extractOne(query: str, choices, scorer=WRatio):
    results = extract(query, choices, scorer=scorer, limit=1)
    return results[0] if results else None


class _Fuzz:
    """Namespace `fuzz` (rapidfuzz espone funzioni di modulo)."""

    ratio = staticmethod(ratio)
    partial_ratio = staticmethod(partial_ratio)
    token_sort_ratio = staticmethod(token_sort_ratio)
    token_set_ratio = staticmethod(token_set_ratio)
    WRatio = staticmethod(WRatio)


class _Process:
    """Namespace `process`."""

    extract = staticmethod(extract)
    extractOne = staticmethod(extractOne)


fuzz = _Fuzz()
process = _Process()
