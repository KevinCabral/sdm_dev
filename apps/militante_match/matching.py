"""Eleitor ↔ Militante fuzzy matching algorithm.

Strategy
--------
For each `Eleitores` row we compute a confidence score (0-100) against
candidate `Militantes` using:

* ``score_nome``  — fuzzy similarity between ``eleitor.nome`` and
  ``militante.nome_completo`` (token-based, accent/case insensitive).
* ``score_pai``   — similarity between father parsed from ``filiacao``
  and ``militante.nm_pai``.
* ``score_mae``   — similarity between mother parsed from ``filiacao``
  and ``militante.nm_mae``.
* ``dt_match``    — exact equality of ``data_nascimento`` /
  ``dt_nascimento``.

Final score:
    35 * nome + 15 * pai + 15 * mae + 35 * dt_bonus
where each component is normalized to 0-1 and dt_bonus is 1 if the dates
match, 0 otherwise. Components without data on either side are dropped
from the denominator (so we don't unfairly penalise records with no
parent name on file).

Blocking
--------
Comparing every eleitor against every militante is O(N*M). To stay
tractable we *block* candidates by:

* If both have ``data_nascimento`` → look up militantes with the SAME
  birth date (fast index lookup).
* Else → look up militantes whose normalized name shares the eleitor's
  first OR last name token.

Only candidates surviving a block are scored.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Iterator

from apps.eleitores.models import Eleitores
from apps.militantes.models import Militantes


# Default thresholds (0-100). Anything below MIN_SCORE is discarded;
# anything ≥ AUTO_CONFIRM_SCORE is auto-confirmed (status=confirmed).
MIN_SCORE = 65.0
AUTO_CONFIRM_SCORE = 92.0

# Stopwords ignored when building blocking tokens.
_STOPWORDS = {
    "DA", "DE", "DO", "DAS", "DOS", "E", "DI", "DU", "LA", "LE",
    "VAN", "VON", "DEL", "MC", "Y", "SAN", "STA", "SAO",
}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_NON_ALPHA = re.compile(r"[^A-Z\s]+")
_MULTISPACE = re.compile(r"\s+")


def normalize_name(s: str | None) -> str:
    """Uppercase, strip accents and punctuation, collapse whitespace."""
    if not s:
        return ""
    out = _strip_accents(str(s)).upper()
    out = _NON_ALPHA.sub(" ", out)
    return _MULTISPACE.sub(" ", out).strip()


def parse_filiacao(raw: str | None) -> tuple[str, str]:
    """Split ``"PAI***MAE"`` style strings.

    Returns ``(pai, mae)`` with empty strings for missing sides.
    Tolerates one or two/three asterisks as separator.
    """
    if not raw:
        return "", ""
    s = str(raw).strip()
    # Accept *, **, ***, **** as separator.
    parts = re.split(r"\*{1,}", s, maxsplit=1)
    if len(parts) == 1:
        # No separator → treat as single name (assume mother by convention).
        return "", parts[0].strip()
    pai, mae = parts[0].strip(), parts[1].strip()
    return pai, mae


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def _token_set_ratio(a: str, b: str) -> float:
    """Token-set similarity à la fuzzywuzzy, in [0, 100]."""
    if not a or not b:
        return 0.0
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    inter = " ".join(sorted(ta & tb))
    only_a = " ".join(sorted(ta - tb))
    only_b = " ".join(sorted(tb - ta))
    s1 = (inter + " " + only_a).strip()
    s2 = (inter + " " + only_b).strip()
    # SequenceMatcher gives a [0,1] ratio; combine with simple ratio for safety.
    r1 = SequenceMatcher(None, s1, s2).ratio()
    r2 = SequenceMatcher(None, a, b).ratio()
    return max(r1, r2) * 100.0


def name_score(a: str | None, b: str | None) -> float:
    return _token_set_ratio(normalize_name(a), normalize_name(b))


# ---------------------------------------------------------------------------
# Aggregate scoring
# ---------------------------------------------------------------------------

@dataclass
class MatchScore:
    score: float
    score_nome: float
    score_pai: float
    score_mae: float
    dt_match: bool


def score_pair(eleitor: Eleitores, militante: Militantes) -> MatchScore:
    pai, mae = parse_filiacao(eleitor.filiacao)
    s_nome = name_score(eleitor.nome, militante.nome_completo)
    s_pai = name_score(pai, militante.nm_pai) if (pai and militante.nm_pai) else None
    s_mae = name_score(mae, militante.nm_mae) if (mae and militante.nm_mae) else None
    dt_match = bool(
        eleitor.data_nascimento
        and militante.dt_nascimento
        and eleitor.data_nascimento == militante.dt_nascimento
    )

    # Weighted average over only the components we actually have data for.
    weights = {"nome": 35.0, "pai": 15.0, "mae": 15.0, "dt": 35.0}
    parts: list[tuple[float, float]] = [(weights["nome"], s_nome / 100.0)]
    if s_pai is not None:
        parts.append((weights["pai"], s_pai / 100.0))
    if s_mae is not None:
        parts.append((weights["mae"], s_mae / 100.0))
    # DOB always considered: we have it (1.0) or we don't (0.0). If neither
    # side has a date, drop it from denominator so it doesn't penalise.
    if eleitor.data_nascimento and militante.dt_nascimento:
        parts.append((weights["dt"], 1.0 if dt_match else 0.0))

    total_w = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / total_w * 100.0 if total_w else 0.0

    return MatchScore(
        score=round(score, 2),
        score_nome=round(s_nome, 2),
        score_pai=round(s_pai or 0.0, 2),
        score_mae=round(s_mae or 0.0, 2),
        dt_match=dt_match,
    )


# ---------------------------------------------------------------------------
# Blocking — pre-build indexes over Militantes for fast candidate lookup.
# ---------------------------------------------------------------------------

class MilitanteIndex:
    """In-memory inverted indexes for fast candidate retrieval."""

    def __init__(self, queryset: Iterable[Militantes] | None = None):
        if queryset is None:
            queryset = Militantes.objects.all()
        self.by_id: dict[int, Militantes] = {}
        self.by_dob: dict[object, list[int]] = defaultdict(list)
        self.by_token: dict[str, list[int]] = defaultdict(list)
        for m in queryset:
            self.by_id[m.id] = m
            if m.dt_nascimento:
                self.by_dob[m.dt_nascimento].append(m.id)
            for tok in self._tokens(m.nome_completo):
                self.by_token[tok].append(m.id)

    @staticmethod
    def _tokens(name: str | None) -> set[str]:
        norm = normalize_name(name)
        if not norm:
            return set()
        toks = [t for t in norm.split() if t not in _STOPWORDS and len(t) >= 3]
        if not toks:
            return set()
        # Use first + last meaningful token as blocking keys.
        return {toks[0], toks[-1]}

    def candidates(self, eleitor: Eleitores) -> Iterator[Militantes]:
        seen: set[int] = set()
        if eleitor.data_nascimento:
            for mid in self.by_dob.get(eleitor.data_nascimento, ()):
                if mid not in seen:
                    seen.add(mid)
                    yield self.by_id[mid]
        # Always also consider name-token blocks (catches typos in DOB).
        for tok in self._tokens(eleitor.nome):
            for mid in self.by_token.get(tok, ()):
                if mid not in seen:
                    seen.add(mid)
                    yield self.by_id[mid]


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------

def find_best_matches(
    eleitor: Eleitores,
    index: MilitanteIndex,
    *,
    limit: int = 5,
    min_score: float = MIN_SCORE,
) -> list[tuple[Militantes, MatchScore]]:
    """Return the top ``limit`` candidates for ``eleitor`` above ``min_score``."""
    scored: list[tuple[Militantes, MatchScore]] = []
    for cand in index.candidates(eleitor):
        s = score_pair(eleitor, cand)
        if s.score >= min_score:
            scored.append((cand, s))
    scored.sort(key=lambda t: t[1].score, reverse=True)
    return scored[:limit]
