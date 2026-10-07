"""Forgiving borrower search: any case, any word order, part words and small typos.

Staff type what they heard over the phone ("kila mary", "mery", "7012 33"). Each word of the
query has to match something on the borrower; results are ordered by how well they match.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable

_WORD = re.compile(r"[a-z0-9]+")


def fold(text: str | None) -> str:
    """Lower case without accents, so 'Kéla' and 'KELA' both read 'kela'."""
    if not text:
        return ""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return plain.lower()


def words(text: str | None) -> list[str]:
    return _WORD.findall(fold(text))


def digits(text: str | None) -> str:
    return "".join(c for c in (text or "") if c.isdigit())


def _close(a: str, b: str) -> bool:
    """True when a and b are one edit apart (a letter added, dropped, swapped or changed)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        i = diff[0] if diff else 0
        return len(diff) == 2 and diff[1] == i + 1 and a[i] == b[i + 1] and a[i + 1] == b[i]
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def _word_score(q: str, field_words: list[str]) -> int:
    """How well one query word matches the borrower's words: 4 exact, 3 start, 2 inside, 1 typo, 0 none."""
    best = 0
    for w in field_words:
        if w == q:
            return 4
        if w.startswith(q):
            best = max(best, 3)
        elif len(q) >= 3 and q in w:
            best = max(best, 2)
        elif len(q) >= 4 and (_close(q, w) or _close(q, w[: len(q)])):
            best = max(best, 1)
    return best


def match_score(query: str, name: str, others: Iterable[str | None] = (), numbers: Iterable[str | None] = ()) -> int:
    """0 when the borrower doesn't match; higher is a better match.

    `others` are extra words (employer); `numbers` are phone and NID, matched on their digits so
    '7012 3344', '70123344' and '+675 7012-3344' all find the same person.
    """
    q_words = words(query)
    if not q_words:
        return 1
    name_words = words(name)
    other_words = [w for o in others for w in words(o)]
    number_digits = [digits(n) for n in numbers if n]
    total = 0
    for q in q_words:
        score = _word_score(q, name_words) * 2  # a name match counts for more than an employer match
        if not score:
            score = _word_score(q, other_words)
        if not score and q.isdigit():  # part of a phone or NID number, even while still typing it
            score = 3 if any(q in d for d in number_digits) else 0
        if not score:
            return 0
        total += score
    # The whole number typed with spaces or dashes ("2011-0488-7712", "7012 3344").
    run = digits(query)
    if len(run) >= 5 and not any(run in d for d in number_digits) and all(w.isdigit() for w in q_words):
        return 0
    return total


def rank[T](query: str, items: Iterable[T], score: Callable[[T], int], name: Callable[[T], str], limit: int) -> list[T]:
    scored = [(score(i), i) for i in items]
    hits = [(s, i) for s, i in scored if s > 0]
    hits.sort(key=lambda p: (-p[0], fold(name(p[1]))))
    return [i for _, i in hits[:limit]]
