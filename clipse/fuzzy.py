"""Search matching: forgiving about typos and word order.

The query is split into words, and every word has to be found in the
text - in any order ("dark whoosh" finds "whoosh_dark_02"). Each word is
tried in this order, best first:
  1. as written           ("whoo" in "whoosh_01")
  2. as a word start, letters in order ("wsh" -> "whoosh") - fzf style
  3. with a typo or two   ("woosh", "whsooh", "transtion" -> "transition")
     - one mistake for words of 4-5 letters, two for longer; a swapped pair of
       letters counts as one.
Exact and in-order matches score higher than typo matches, so the best
hit is still on top. Toolkit-agnostic; results are cached per word and
per name, so typing stays fast with thousands of clips.
"""
import re
from functools import lru_cache

import unicodedata

_WORD = re.compile(r"[^\W_]+")             # letters/digits runs ("whoosh", "02")
_SPECIAL_FOLD = {"ø": "o", "æ": "a", "ß": "s", "ł": "l", "đ": "d", "þ": "t", "ð": "d", "œ": "o"}


@lru_cache(maxsize=100000)
def fold(text):
    """Lower case without accents, one character for one ("Lyd_ø Ä" ->
    "lyd_o a"), so "o" finds "ø" and "café" finds "cafe" - and the letters
    to highlight stay where they were."""
    out = []
    for ch in text.lower():
        if ch in _SPECIAL_FOLD:
            out.append(_SPECIAL_FOLD[ch])
            continue
        base = unicodedata.normalize("NFKD", ch)[:1] if ord(ch) > 127 else ch
        out.append(base if base and base.isascii() and base.isalnum() else ch)
    return "".join(out)
_PIECE = re.compile(r"[^\W\d_]+|\d+")       # ...split again into letters / numbers


@lru_cache(maxsize=50000)
def _prepare(text):
    """(lower-case text, [(start, token)]) - tokens are the text's words,
    and numbers / letters split apart ("whoosh02" -> "whoosh", "02")."""
    lower = fold(text)
    tokens = []
    for m in _WORD.finditer(lower):
        tokens.append((m.start(), m.group()))
        pieces = list(_PIECE.finditer(m.group()))
        if len(pieces) > 1:
            tokens.extend((m.start() + p.start(), p.group()) for p in pieces)
    return lower, tuple(tokens)


def _max_typos(word):
    n = len(word)
    if n < 4:
        return 0
    return 1 if n <= 5 else 2


@lru_cache(maxsize=200000)
def _typo_distance(a, b, limit):
    """Edit distance (insert, delete, change, swap two neighbours), or
    limit+1 as soon as it's clear it's above `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
            best = min(best, v)
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _coherent(positions, lower):
    """A match that hops into the middle of another word ("w-h-s" picked out
    of "whoosh hits sharp") is noise; abbreviations inside one word ("wsh"
    -> "whoosh") and word starts ("dw" -> "dark whoosh") are fine."""
    if len(positions) < 2:
        return True
    if not any(not lower[k].isalnum() for k in range(positions[0], positions[-1])):
        return True  # all inside one word
    for a, b in zip(positions, positions[1:]):
        if b != a + 1 and lower[b - 1].isalnum():  # a new run that starts mid-word
            return False
    return True


def _subsequence(word, lower, start=0):
    """fzf-style: the letters in order. (score, positions) or None."""
    positions, i, score, run = [], start, 0.0, 0
    for ch in word:
        found = lower.find(ch, i)
        if found == -1:
            return None
        if positions and found == positions[-1] + 1:
            run += 1
            score += 3 + run
        else:
            run = 0
            score += 1
        if found == 0 or not lower[found - 1].isalnum():
            score += 2
        positions.append(found)
        i = found + 1
    # letters spread far apart are a weak match
    spread = positions[-1] - positions[0] + 1 - len(word)
    return score - spread * 0.5, positions


def _word_match(word, lower, tokens):
    """Best match for one query word: (score, positions) or None."""
    at = lower.find(word)
    if at >= 0:  # 1. as written
        score = 12 + len(word) * 2
        if at == 0 or not lower[at - 1].isalnum():
            score += 6  # starts a word
        if any(start == at and tok == word for start, tok in tokens):
            score += 4  # is a whole word
        return score, list(range(at, at + len(word)))
    sub = _subsequence(word, lower)  # 2. letters in order
    if sub is not None and not _coherent(sub[1], lower):
        sub = None  # scattered across words: not a match worth showing
    if sub is not None and sub[0] >= len(word) * 1.6:
        return sub[0] * 0.8, sub[1]
    limit = _max_typos(word)  # 3. with typos
    if limit:
        best = None
        for start, tok in tokens:
            if len(tok) < 3:
                continue
            # cheap first check: typos rarely change both of the first two letters
            if not (tok[0] == word[0] or tok[1:2] == word[1:2] or (tok[:2] == word[1::-1])):
                continue
            for target in (tok, tok[:len(word)]) if len(tok) > len(word) else (tok,):
                d = _typo_distance(word, target, limit)
                if d <= limit:
                    score = 4 + len(word) - 4 * d - (0.5 if target is not tok else 0)
                    if best is None or score > best[0]:
                        best = (score, list(range(start, start + len(target))))
        if best is not None:
            return best
    if sub is not None:  # weak in-order match - better than nothing
        return sub[0] * 0.5, sub[1]
    return None


@lru_cache(maxsize=200000)
def _hit(word, text):
    lower, tokens = _prepare(text)
    return _word_match(word, lower, tokens)


def smart_score(query, text):
    """Score of `text` for `query` (higher = better), or None if some word
    of the query isn't in it at all."""
    words = fold(query).split()
    if not words:
        return 0
    if not text:
        return None
    lower = _prepare(text)[0]
    total, last_pos, in_order = 0.0, -1, True
    for word in words:
        hit = _hit(word, text)
        if hit is None:
            return None
        total += hit[0]
        if hit[1] and hit[1][0] < last_pos:
            in_order = False
        last_pos = hit[1][-1] if hit[1] else last_pos
    phrase = " ".join(words)
    stem = lower.rsplit(".", 1)[0] if "." in lower[-6:] else lower
    if stem == phrase or lower == phrase:
        total += 30  # the whole name, exactly
    elif lower.startswith(phrase):
        total += 8
    if len(words) > 1:
        if in_order:
            total += 4
        if phrase in lower or phrase.replace(" ", "_") in lower or phrase.replace(" ", "") in lower:
            total += 10
    return total - len(lower) * 0.01


# kept under the old name - other code calls it
fuzzy_score = smart_score

_bits = int.bit_count if hasattr(int, "bit_count") else (lambda n: bin(n).count("1"))


@lru_cache(maxsize=200000)
def _letters(text):
    """Which letters and digits are in `text`, as bits."""
    mask = 0
    for ch in set(fold(text)):
        if ch.isalnum():
            mask |= 1 << (ord(ch) % 61)
    return mask


def scorer(query):
    """text -> score (or None), with the same answers as smart_score(query,
    text) - set up once for a search, so thousands of names go through
    quickly. Most names can't match at all, and that shows without
    looking closely: a word is found as written, as letters in order, or
    with at most one or two typos, so a name that lacks more of the
    word's letters than typos are allowed is out."""
    words = fold(query).split()
    if not words:
        return lambda text: 0
    needs = [(_letters(word), _max_typos(word)) for word in words]

    def score(text):
        if not text:
            return None
        have = _letters(text)
        for mask, typos in needs:
            missing = mask & ~have
            if missing and _bits(missing) > typos:
                return None
        return smart_score(query, text)
    return score


def match_positions(query, text):
    """Which characters of `text` to highlight for `query`."""
    words = fold(query).split()
    if not words or not text:
        return set()
    positions = set()
    for word in words:
        hit = _hit(word, text)
        if hit:
            positions.update(hit[1])
    return positions
