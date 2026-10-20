"""Riconoscimento della carta base a partire dal testo letto dall'immagine.

Ordine di priorita':
  1. nome originale stampato sotto il titolo (tipico dei proxy);
  2. titolo della carta, se coincide con una carta esistente;
  3. confronto fuzzy del testo delle regole con il testo Oracle del database.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # rapidfuzz e' una estensione C: su Android non e' compilabile.
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - dipende dall'ambiente
    from . import _fuzzshim as _fallback

    fuzz = _fallback.fuzz
    process = _fallback.process

from .carddb import CardDB, CardInfo
from .ocr import TYPE_WORDS, CardReading
from .textutil import normalize_for_compare, normalize_plain


@dataclass
class Candidate:
    card: CardInfo
    score: float
    # Chiave di traduzione (es. "reason.title"): il testo viene risolto dalla GUI
    # cosi' un cambio di lingua aggiorna anche i motivi gia' calcolati.
    reason: str


class Matcher:
    """Motore di riconoscimento basato sull'indice delle carte."""

    def __init__(self, db: CardDB):
        self.db = db
        self._names = db.names()
        self._name_keys = [normalize_plain(name) for name in self._names]
        self._oracles = [normalize_for_compare(card.oracle) for card in db.cards]

    # ---------- ricerca per nome (usata anche dalla GUI) ----------

    def search_names(self, query: str, limit: int = 20) -> list[str]:
        """Ricerca per nome tollerante: "animar" trova "Animar, Soul of Elements"."""
        query = query.strip()
        if not query:
            return self._names[:limit]
        exact = self.db.by_name(query)
        results = process.extract(
            normalize_plain(query), self._name_keys, scorer=fuzz.WRatio, limit=limit
        )
        names = [self._names[index] for _, _, index in results]
        if exact and exact.name not in names:
            names.insert(0, exact.name)
        return names

    # ---------- riconoscimento ----------

    def match(self, reading: CardReading, limit: int = 6) -> list[Candidate]:
        results: list[Candidate] = []
        seen: set[str] = set()

        def add(card: CardInfo, score: float, reason: str) -> None:
            key = normalize_plain(card.name)
            if key in seen:
                return
            seen.add(key)
            results.append(Candidate(card=card, score=score, reason=reason))

        if reading.base_hint:
            card, score = self._best_name(reading.base_hint, scorer=fuzz.WRatio)
            if card is not None and score >= 80:
                add(card, max(score, 96.0), "reason.base_hint")

        if reading.title:
            card, score = self._best_name(reading.title)
            if card is not None and score >= 80:
                add(card, score, "reason.title")

        if reading.rules_text.strip():
            for card, score in self._best_rules(reading, limit):
                add(card, score, "reason.rules")

        results.sort(key=lambda item: -item.score)
        return results[:limit]

    def _best_name(self, text: str, scorer=fuzz.ratio) -> tuple[CardInfo | None, float]:
        key = normalize_plain(text)
        exact = self.db.by_name(text)
        if exact is not None:
            return exact, 100.0
        if not key:
            return None, 0.0
        best = process.extractOne(key, self._name_keys, scorer=scorer)
        if best is None:
            return None, 0.0
        _, score, index = best
        return self.db.cards[index], float(score)

    def _best_rules(self, reading: CardReading, limit: int) -> list[tuple[CardInfo, float]]:
        query = normalize_for_compare(reading.rules_text)
        if len(query) < 25:
            return []
        pool = min(len(self._oracles), 4000)
        by_set = process.extract(
            query, self._oracles, scorer=fuzz.token_set_ratio, limit=pool
        )
        by_order = process.extract(
            query, self._oracles, scorer=fuzz.token_sort_ratio, limit=pool
        )
        combined: dict[int, float] = {}
        for _, score, index in by_set:
            combined[index] = 0.65 * score
        for _, score, index in by_order:
            combined[index] = combined.get(index, 0.0) + 0.35 * score

        scored = sorted(combined.items(), key=lambda item: -item[1])
        out: list[tuple[CardInfo, float]] = []
        for index, score in scored[: limit * 4]:
            card = self.db.cards[index]
            if not card.oracle.strip():
                continue
            adjusted = min(99.0, score + self._type_bonus(card, reading.type_line))
            out.append((card, adjusted))
        out.sort(key=lambda item: -item[1])
        return out[:limit]

    @staticmethod
    def _type_bonus(card: CardInfo, type_line: str) -> float:
        lowered = type_line.lower()
        if not lowered:
            return 0.0
        card_types = card.types.lower()
        for word in TYPE_WORDS:
            if word in lowered and word in card_types:
                return 4.0
        return 0.0


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


def token_types(type_line: str) -> str:
    """Tipi ricavati dalla linea dei tipi di un token.

    "Token Creature - Beast" diventa "creature beast": la parola "token" non
    esiste nel campo Types degli script e va tolta.
    """
    words = [w for w in normalize_for_compare(type_line).split() if w != "token"]
    return " ".join(words)


class TokenMatcher:
    """Riconoscimento del token base a partire da tipo, P/T e regole lette.

    Il titolo letto e' il nuovo nome (il re-skin), quindi non serve a trovare
    la base: si confrontano la linea dei tipi, la forza/costituzione e il testo
    delle regole con quelli degli script in res/tokenscripts.
    """

    def __init__(self, db: CardDB):
        self.db = db
        self._types = [normalize_for_compare(card.types) for card in db.cards]
        self._oracles = [normalize_for_compare(card.oracle) for card in db.cards]
        self._name_keys = [normalize_plain(name) for name in db.names()]

    def search_names(self, query: str, limit: int = 20) -> list[str]:
        """Ricerca per nome tra i token (tollera il suffisso "Token")."""
        query = query.strip()
        names = self.db.names()
        if not query:
            return names[:limit]
        exact = self.db.by_name(query) or self.db.by_name(f"{query} Token")
        results = process.extract(
            normalize_plain(query), self._name_keys, scorer=fuzz.WRatio, limit=limit
        )
        out = [names[index] for _, _, index in results]
        if exact is not None and exact.name not in out:
            out.insert(0, exact.name)
        return out

    def match(self, reading: CardReading, limit: int = 6) -> list[Candidate]:
        results: list[Candidate] = []
        seen: set[str] = set()

        def add(card: CardInfo, score: float, reason: str) -> None:
            key = normalize_plain(card.name)
            if key in seen:
                return
            seen.add(key)
            results.append(Candidate(card=card, score=score, reason=reason))

        for text in (reading.base_hint, reading.title):
            if not text:
                continue
            card, score = self._best_name(text)
            if card is not None and score >= 86:
                add(card, score, "reason.token_name")

        for card, score in self._best_shape(reading, limit):
            add(card, score, "reason.type")

        results.sort(key=lambda item: -item.score)
        return results[:limit]

    def _best_name(self, text: str) -> tuple[CardInfo | None, float]:
        exact = self.db.by_name(text) or self.db.by_name(f"{text} Token")
        if exact is not None:
            return exact, 100.0
        key = normalize_plain(text)
        if not key:
            return None, 0.0
        best = process.extractOne(key, self._name_keys, scorer=fuzz.WRatio)
        if best is None:
            return None, 0.0
        _, score, index = best
        return self.db.cards[index], float(score)

    def _best_shape(self, reading: CardReading, limit: int) -> list[tuple[CardInfo, float]]:
        query_types = token_types(reading.type_line)
        query_pt = reading.pt.strip()
        query_rules = normalize_for_compare(reading.rules_text)
        scored: list[tuple[CardInfo, float]] = []
        for index, card in enumerate(self.db.cards):
            if query_types and self._types[index]:
                type_score = fuzz.token_sort_ratio(query_types, self._types[index])
            else:
                type_score = 0.0
            if query_pt:
                pt_score = 100.0 if card.pt.strip() == query_pt else 0.0
            else:
                pt_score = 100.0 if not card.pt.strip() else 0.0
            if query_rules:
                oracle = self._oracles[index]
                rules_score = fuzz.token_set_ratio(query_rules, oracle) if oracle else 0.0
            else:
                # nessun testo letto: meglio un token senza abilita' (vanilla)
                rules_score = 100.0 if not self._oracles[index] else 45.0
            score = 0.45 * type_score + 0.25 * pt_score + 0.30 * rules_score
            # soglia alta: un tipo letto male non deve far scegliere in automatico
            # il token sbagliato (meglio "base da scegliere" e intervento manuale).
            if score >= 80.0:
                scored.append((card, score))
        scored.sort(key=lambda item: -item[1])
        return scored[:limit]
