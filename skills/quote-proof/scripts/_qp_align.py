"""Locate a quote in a source: exact, normalized (with recorded steps) or approximate (sequence alignment)."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Tuple

from _qp_normalize import (CJK_SPACING, Normalized, has_cjk, is_cjk, normalize, split_ellipsis, step_names,
                           steps_for_match)
from _qp_sources import SourceText

MAX_OCCURRENCES = 50
FULL_SCAN_MAX_WINDOWS = 1500     # up to this many windows the best window is found by scanning all of them
MIN_NARROW_UNITS = 5             # quotes with fewer words (or fewer characters, see below) are always scanned in full
MIN_NARROW_CHARS = 8
MAX_CANDIDATE_WINDOWS = 400
_WORD_RE = re.compile(r"\w+")


@dataclass
class Match:
    """A place in a source where a quote was found."""
    verdict: str                     # exact | normalized | approximate
    start: int                       # original offsets [start, end) in the source text
    end: int
    line_start: int
    line_end: int
    page_start: int
    page_end: int
    text: str                        # original source text of the span
    steps: List[str]
    ratio: Optional[float] = None
    changed_units: Optional[int] = None
    unit: Optional[str] = None


def _make(src: SourceText, start: int, end: int, verdict: str, steps: List[str], ratio: Optional[float] = None,
          changed: Optional[int] = None, unit: Optional[str] = None) -> Match:
    last = max(end - 1, start)
    return Match(verdict, start, end, src.line_at(start), src.line_at(last), src.page_at(start), src.page_at(last),
                 src.text[start:end], steps, ratio, changed, unit)


def clean_slice(text: str) -> str:
    """A source span as a one-line quote: hyphenated line breaks joined, blockquote markers and line breaks folded."""
    t = re.sub(r"(?<=[^\W\d_])-[ \t]*\r?\n[ \t]*(?=[^\W\d_])", "", text)
    t = re.sub(r"\n[ \t]*>+[ \t]?", " ", t)
    return " ".join(t.split())


def variant_keys(quote: str, src: SourceText) -> List[Tuple[bool, bool]]:
    """Normalization variants worth trying for this quote and source (joined/kept hyphen x CJK spacing)."""
    keys = [(True, False)]
    if src.has_hyphen_break:
        keys.append((False, False))
    if src.has_cjk and has_cjk(quote):
        keys.append((True, True))
        if src.has_hyphen_break:
            keys.append((False, True))
    return keys


def find_exact(quote: str, src: SourceText, limit: int = MAX_OCCURRENCES) -> List[Match]:
    """Every place (up to ``limit``) where the quote appears character for character."""
    found: List[Match] = []
    pos = src.text.find(quote)
    while pos != -1 and len(found) < limit:
        found.append(_make(src, pos, pos + len(quote), "exact", [], 1.0, 0))
        pos = src.text.find(quote, pos + 1)
    return found


def _fragments(quote: str, join_hyphen: bool, cjk_strip: bool) -> List[Tuple[Normalized, int, int]]:
    out = []
    for part in split_ellipsis(quote):
        qn = normalize(part, join_hyphen, cjk_strip)
        a, b = qn.trim()
        if b > a:
            out.append((qn, a, b))
    return out


def find_normalized(quote: str, src: SourceText, limit: int = MAX_OCCURRENCES) -> List[Match]:
    """Every place where the quote matches after normalization. Fragments split by ``[...]`` must appear in order."""
    for join_hyphen, cjk_strip in variant_keys(quote, src):
        frags = _fragments(quote, join_hyphen, cjk_strip)
        if not frags:
            continue
        sn = src.variant(join_hyphen, cjk_strip)
        text = sn.text
        first, fa, fb = frags[0]
        needle = first.text[fa:fb]
        found: List[Match] = []
        pos = text.find(needle)
        while pos != -1 and len(found) < limit:
            starts = [pos]
            cursor = pos + len(needle)
            ok = True
            for qn, a, b in frags[1:]:
                k = text.find(qn.text[a:b], cursor)
                if k == -1:
                    ok = False
                    break
                starts.append(k)
                cursor = k + (b - a)
            if ok:
                flags = 0
                for (qn, a, b), k in zip(frags, starts):
                    flags |= steps_for_match(qn, a, b - a, sn, k)
                last_len = frags[-1][2] - frags[-1][1]
                s0, _ = sn.span(starts[0], starts[0] + 1)
                _, e1 = sn.span(starts[-1], starts[-1] + last_len)
                found.append(_make(src, s0, e1, "normalized", step_names(flags, len(frags) > 1), 1.0, 0))
            pos = text.find(needle, pos + 1)
        if found:
            return found
    return []


# ---------- approximate alignment ----------

def _units(src: SourceText, key: Tuple[bool, bool], char_mode: bool):
    """Alignment units of a source variant: (unit strings, [(start, end)] offsets in the normalized text)."""
    def make():
        text = src.variant(*key).text
        if char_mode:
            pos = [(i, i + 1) for i, c in enumerate(text) if c != " "]
        else:
            pos = [(m.start(), m.end()) for m in _WORD_RE.finditer(text)]
        return [text[a:b] for a, b in pos], pos
    return src.cache(("units", key, char_mode), make)


def _ngram_index(src: SourceText, key: Tuple[bool, bool], char_mode: bool, n: int):
    def make():
        units = _units(src, key, char_mode)[0]
        index = {}
        for i in range(len(units) - n + 1):
            index.setdefault(tuple(units[i:i + n]), []).append(i)
        return index
    return src.cache(("ngrams", key, char_mode, n), make)


def _is_char_mode(quote: str) -> bool:
    letters = [c for c in quote if c.isalnum()]
    return bool(letters) and sum(1 for c in letters if is_cjk(c)) * 2 >= len(letters)


def window_ratios(q_units: Sequence[str], units: Sequence[str], starts: Sequence[int]) -> Tuple[float, int]:
    """Best (ratio, start) over window starts; ties go to the lowest start. autojunk is off on purpose: with it
    on, SequenceMatcher ignores frequent tokens in sequences of 200+ items and long repetitive quotes mismatch."""
    w = len(q_units)
    sm = SequenceMatcher(None, autojunk=False)
    sm.set_seq2(list(q_units))
    best_r, best_s = -1.0, 0
    for s in starts:
        sm.set_seq1(units[s:s + w])
        r = sm.ratio()
        if r > best_r:
            best_r, best_s = r, s
    return best_r, best_s


def candidate_starts(q_units: Sequence[str], index: dict, n: int, n_windows: int) -> List[int]:
    """Window starts that share at least one n-gram with the quote at a compatible offset (+-1)."""
    counts: Counter = Counter()
    for k in range(len(q_units) - n + 1):
        for p in index.get(tuple(q_units[k:k + n]), ()):
            for d in (-1, 0, 1):
                t = p - k + d
                if 0 <= t < n_windows:
                    counts[t] += 1
    top = sorted(counts, key=lambda t: (-counts[t], t))[:MAX_CANDIDATE_WINDOWS]
    return sorted(top)


def best_window(q_units: Sequence[str], src: SourceText, key: Tuple[bool, bool], char_mode: bool,
                full_scan: bool = False) -> Tuple[Optional[float], int]:
    """Best window of the source variant for the quote units: (ratio or None when nothing is close, start)."""
    units = _units(src, key, char_mode)[0]
    w = len(q_units)
    n_windows = max(1, len(units) - w + 1)
    n = 3 if char_mode else 2
    if full_scan or n_windows <= FULL_SCAN_MAX_WINDOWS or w < (MIN_NARROW_CHARS if char_mode else MIN_NARROW_UNITS):
        starts: Sequence[int] = range(n_windows)
    else:
        starts = candidate_starts(q_units, _ngram_index(src, key, char_mode, n), n, n_windows)
        if not starts:
            return None, 0
    return window_ratios(q_units, units, starts)


def find_approximate(quote: str, src: SourceText, min_ratio: float, full_scan: bool = False
                     ) -> Tuple[Optional[Match], Optional[float]]:
    """Closest passage of the source. Returns (match when ratio >= min_ratio, best ratio seen)."""
    joined = " ".join(split_ellipsis(quote))
    char_mode = _is_char_mode(joined)
    best: Optional[Tuple[float, int, Tuple[bool, bool], List[str]]] = None
    for key in [(True, False)] + ([(False, False)] if src.has_hyphen_break else []):
        qn = normalize(joined, *key)
        a, b = qn.trim()
        qtext = qn.text[a:b]
        if char_mode:
            q_units = [c for c in qtext if c != " "]
        else:
            q_units = _WORD_RE.findall(qtext)
        if len(q_units) < 2:
            continue
        ratio, start = best_window(q_units, src, key, char_mode, full_scan)
        if ratio is not None and (best is None or ratio > best[0]):
            best = (ratio, start, key, q_units)
    if best is None:
        return None, None
    ratio, start, key, q_units = best
    if ratio < min_ratio:
        return None, round(ratio, 3)
    units, pos = _units(src, key, char_mode)
    w = len(q_units)
    # A slightly longer window lets symbol tokens (the source's "&") sit between matched words
    # without pushing the end of the range past what the quote says.
    window = units[start:start + w + 2]
    sm = SequenceMatcher(None, q_units, window, autojunk=False)
    ops = [list(op) for op in sm.get_opcodes()]
    while ops and ops[-1][0] == "insert":
        ops.pop()
    while ops and ops[0][0] == "insert":
        ops.pop(0)
    if ops and ops[-1][0] == "replace":  # never grow the range beyond the quote's own length
        ops[-1][4] = min(ops[-1][4], ops[-1][3] + ops[-1][2] - ops[-1][1])
    if ops and ops[0][0] == "replace":
        ops[0][3] = max(ops[0][3], ops[0][4] - (ops[0][2] - ops[0][1]))
    spans = [op for op in ops if op[4] > op[3]]
    if not spans:
        return None, round(ratio, 3)
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in ops if op != "equal")
    first, last = start + spans[0][3], start + spans[-1][4] - 1
    sn = src.variant(*key)
    s0, _ = sn.span(pos[first][0], pos[first][0] + 1)
    _, e1 = sn.span(pos[last][1] - 1, pos[last][1])
    if char_mode and changed == 0:
        return _make(src, s0, e1, "normalized", step_names(CJK_SPACING), 1.0, 0), 1.0
    unit = "char" if char_mode else "word"
    return _make(src, s0, e1, "approximate", [], round(ratio, 3), changed, unit), round(ratio, 3)
