"""Riconoscimento della carta base a partire dal testo letto dall'immagine.

Ordine di priorita':
  1. nome originale stampato sotto il titolo (tipico dei proxy);
  2. titolo della carta, se coincide con una carta esistente;
  3. confronto fuzzy del testo delle regole con il testo Oracle del database.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

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
        return [card.name for card in self.search_candidates(query, limit)]

    def search_candidates(self, query: str, limit: int = 20) -> list[CardInfo]:
        """Come search_names, ma restituisce le carte invece dei soli nomi.

        Il nome da solo non basta a scegliere la base: in Forge piu' script
        possono chiamarsi allo stesso modo (tre "Citizen Token" con P/T e
        colori diversi). La GUI ha bisogno dell'oggetto per mostrare tipo, P/T
        e file, e per usare davvero la base scelta.
        """
        query = query.strip()
        if not query:
            return list(self.db.cards[:limit])
        exact = self.db.by_name(query)
        results = process.extract(
            normalize_plain(query), self._name_keys, scorer=fuzz.WRatio, limit=limit
        )
        cards = [self.db.cards[index] for _, _, index in results]
        if exact is not None and all(card.entry != exact.entry for card in cards):
            cards.insert(0, exact)
        return cards

    # ---------- riconoscimento ----------

    def match_name(self, text: str) -> tuple[CardInfo | None, float]:
        """Migliore carta per nome, con punteggio.

        Usato per agganciare un emblema al suo Planeswalker partendo dal nome
        ricavato dal file o dal titolo letto.
        """
        return self._best_name(text)

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
        return [card.name for card in self.search_candidates(query, limit)]

    def search_candidates(self, query: str, limit: int = 20) -> list[CardInfo]:
        """Vedi Matcher.search_candidates: la ricerca deve poter distinguere i
        token omonimi (es. "Citizen Token" 2/2 e "Citizen Token" 1/1 G,W)."""
        query = query.strip()
        if not query:
            return list(self.db.cards[:limit])
        exact = self.db.by_name(query) or self.db.by_name(f"{query} Token")
        results = process.extract(
            normalize_plain(query), self._name_keys, scorer=fuzz.WRatio, limit=limit
        )
        cards = [self.db.cards[index] for _, _, index in results]
        if exact is not None and all(card.entry != exact.entry for card in cards):
            cards.insert(0, exact)
        return cards

    def match(self, reading: CardReading, limit: int = 6) -> list[Candidate]:
        results: list[Candidate] = []
        by_key: dict[str, Candidate] = {}

        def add(card: CardInfo, score: float, reason: str) -> None:
            # Chiave sullo script, non sul nome: piu' token omonimi (es. tre
            # "Citizen Token") devono comparire tutti tra i candidati, perche'
            # solo P/T e tipo dicono quale usa la carta di partenza.
            key = f"{card.source}|{card.entry}"
            previous = by_key.get(key)
            if previous is None:
                candidate = Candidate(card=card, score=score, reason=reason)
                by_key[key] = candidate
                results.append(candidate)
            elif score > previous.score:
                # Lo stesso script puo' arrivare dal nome (ipotesi prudente) e
                # poi dalla forma, che e' piu' affidabile: vale la prova piu'
                # forte. Senza questo aggiornamento il token giusto resta
                # congelato a un punteggio basso e un omonimo lo supera.
                previous.score = score
                previous.reason = reason

        for text in (reading.base_hint, reading.title):
            if not text:
                continue
            candidate = self._best_name(text, reading)
            if candidate is not None and candidate.score >= 86:
                add(candidate.card, candidate.score, candidate.reason)

        for card, score in self._best_shape(reading, limit):
            add(card, score, "reason.type")

        results.sort(key=lambda item: -item.score)
        self._flag_ambiguous(results, reading)
        return results[:limit]

    def _flag_ambiguous(self, results: list[Candidate], reading: CardReading) -> None:
        """Segnala i token che piu' script omonimi possono rappresentare.

        I due "Citizen Token" 1/1 differiscono solo per i colori (bianco e
        verde-bianco), che l'OCR non legge: la scelta non puo' essere
        automatica, quindi la riga non deve risultare pronta. Il punteggio
        resta quello della forma: abbassarlo farebbe scavalcare i candidati
        ambigui da token che somigliano molto meno.
        """
        if not results:
            return
        key = normalize_plain(results[0].card.name)
        variants = [
            card
            for card in self.db.cards
            if normalize_plain(card.name) == key and self._shape_matches(card, reading)
        ]
        variants = self._narrow_by_rules(variants, reading)
        if len(variants) < 2:
            return
        for candidate in results:
            if any(candidate.card.entry == variant.entry for variant in variants):
                candidate.reason = "reason.token_ambiguous"

    def _best_name(self, text: str, reading: CardReading) -> Candidate | None:
        """Candidato dedotto dal nome letto (senza il aiuto della forma)."""
        exact = self.db.by_name(text) or self.db.by_name(f"{text} Token")
        if exact is not None:
            return self._from_namesakes(exact, reading, 100.0)
        key = normalize_plain(text)
        if not key:
            return None
        best = process.extractOne(key, self._name_keys, scorer=fuzz.WRatio)
        if best is None:
            return None
        _, score, index = best
        return self._from_namesakes(self.db.cards[index], reading, float(score))

    def _from_namesakes(
        self, card: CardInfo, reading: CardReading, score: float
    ) -> Candidate:
        """Sceglie tra gli script che condividono lo stesso "Name:".

        In Forge tre script si chiamano "Citizen Token" (2/2, 1/1 G,W e 1/1 W):
        l'indice per nome restituisce sempre il primo, che spesso non e' il
        token usato dalla carta importata. P/T e tipo letti dall'immagine
        indicano quello giusto; se restano piu' candidati il punteggio viene
        abbassato, cosi' la riga resta da controllare e si sceglie a mano.
        Quando l'immagine non basta a distinguerli (i colori non si leggono)
        vale l'ordine dei file, che non dipende dal filesystem e quindi non
        cambia da una macchina all'altra.
        """
        key = normalize_plain(card.name)
        same = sorted(
            (c for c in self.db.cards if normalize_plain(c.name) == key),
            key=lambda c: c.entry.lower(),
        )
        if len(same) < 2:
            return Candidate(card=card, score=score, reason="reason.token_name")
        matching = [c for c in same if self._shape_matches(c, reading)] or same
        matching = self._narrow_by_rules(matching, reading)
        if len(matching) == 1:
            return Candidate(card=matching[0], score=score, reason="reason.token_name")
        return Candidate(
            card=matching[0],
            score=min(score, 88.0),
            reason="reason.token_ambiguous",
        )

    def _narrow_by_rules(self, cards: list[CardInfo], reading: CardReading) -> list[CardInfo]:
        """Riduce gli omonimi usando il testo regole quando basta a distinguerli.

        Molti token condividono nome, tipi e P/T; in EVA succede ad esempio con
        alcuni "Angel" e soprattutto con i "Pilot". In questi casi il testo
        Oracle e' l'unico indizio affidabile rimasto. L'OCR sui token e' spesso
        rumoroso, quindi il filtraggio parte solo quando il miglior match e'
        chiaramente sopra gli altri.
        """
        if len(cards) < 2:
            return cards
        query = normalize_for_compare(reading.rules_text)
        if len(query) < 12:
            return cards

        exact = [card for card in cards if normalize_for_compare(card.oracle) == query]
        if len(exact) == 1:
            return exact

        scored: list[tuple[float, CardInfo]] = []
        for card in cards:
            oracle = normalize_for_compare(card.oracle)
            if not oracle:
                continue
            set_score = fuzz.token_set_ratio(query, oracle)
            sort_score = fuzz.token_sort_ratio(query, oracle)
            scored.append((0.65 * set_score + 0.35 * sort_score, card))

        if len(scored) < 2:
            return cards

        scored.sort(key=lambda item: -item[0])
        best_score, best_card = scored[0]
        second_score = scored[1][0]
        if best_score < 82 or (best_score - second_score) < 6:
            return cards
        return [best_card]

    @staticmethod
    def _shape_matches(card: CardInfo, reading: CardReading) -> bool:
        """Vero se P/T e tipi dello script concordano con quanto letto."""
        query_pt = reading.pt.strip()
        if query_pt and card.pt.strip() != query_pt:
            return False
        query_types = token_types(reading.type_line)
        if query_types:
            ratio = fuzz.token_sort_ratio(
                query_types, normalize_for_compare(card.types)
            )
            if ratio < 80:
                return False
        return True

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
                # token_set_ratio da' 100 anche quando il token ha abilita' in
                # piu' che l'immagine non mostra ("Flying" vale come "Flying,
                # Vigilance"): la media con token_sort_ratio penalizza le
                # parole mancanti, che sono proprio quelle che distinguono due
                # token omonimi (Angelo vigilante e non).
                if oracle:
                    rules_score = (
                        fuzz.token_set_ratio(query_rules, oracle)
                        + fuzz.token_sort_ratio(query_rules, oracle)
                    ) / 2
                else:
                    rules_score = 0.0
            else:
                # nessun testo letto: meglio un token senza abilita' (vanilla)
                rules_score = 100.0 if not self._oracles[index] else 45.0
            score = 0.45 * type_score + 0.25 * pt_score + 0.30 * rules_score
            # soglia alta: un tipo letto male non deve far scegliere in automatico
            # il token sbagliato (meglio "base da scegliere" e intervento manuale).
            if score >= 80.0:
                scored.append((card, score))
        # A parita' di punteggio decide il nome del file: la scelta non deve
        # dipendere dall'ordine con cui il database elenca le carte.
        scored.sort(key=lambda item: (-item[1], item[0].entry.lower()))
        return scored[:limit]
