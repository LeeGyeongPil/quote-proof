"""Text normalization with an exact map back to the original text.

``normalize()`` folds the differences that printing and copying introduce (line breaks, hyphenated line
ends, curly quotes, Markdown markup, ...) but never touches the wording. Every normalized character keeps

* ``ostart`` / ``oend``: the original offsets of the character itself,
* ``rstart``: the original offset where the characters removed right before it begin (dropped hyphens,
  whitespace, markup), so two aligned characters can be compared as raw text,
* ``flags``: which normalization steps touched it or the characters removed before it.

``steps_for_match()`` uses those to report only the steps that were needed inside a matched span.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from typing import List, Tuple

NFKC, QUOTES, DASHES, WHITESPACE, DEHYPHEN, CASE, MD_MARKUP, CJK_SPACING = 1, 2, 4, 8, 16, 32, 64, 128

STEP_ORDER = ["nfkc", "quotes", "dashes", "whitespace", "dehyphen", "case", "md_markup", "ellipsis", "cjk_spacing"]
_FLAG_NAMES = [(NFKC, "nfkc"), (QUOTES, "quotes"), (DASHES, "dashes"), (WHITESPACE, "whitespace"),
               (DEHYPHEN, "dehyphen"), (CASE, "case"), (MD_MARKUP, "md_markup"), (CJK_SPACING, "cjk_spacing")]

QUOTE_MAP = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
             "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"'}
DASH_CHARS = "–—−‒―"
HYPHEN_CHARS = "-‐‑"
ELLIPSIS_SPLIT_RE = re.compile(r"\s*(?:\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…)\s*")
# runs of characters that no step can change (lowercase ASCII, digits, common punctuation): copied in bulk
_PLAIN_RE = re.compile(r"[a-z0-9.,;:!?()'\"/\[\]{}=+%&@$|<#]+")
_HYPHEN_BREAK_RE = re.compile(r"[^\W\d_]-[ \t]*\r?\n[ \t]*[^\W\d_]")


def is_cjk(ch: str) -> bool:
    """True for Hangul, kana and Han characters (text written without spaces between words)."""
    o = ord(ch)
    return (0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0x3040 <= o <= 0x30FF
            or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xFF66 <= o <= 0xFF9F)


def has_cjk(text: str) -> bool:
    return any(is_cjk(c) for c in text)


def has_hyphen_break(text: str) -> bool:
    """True when the text contains a word split across lines with a hyphen (or a soft hyphen)."""
    return bool(_HYPHEN_BREAK_RE.search(text)) or "\u00ad" in text


def step_names(flags: int, ellipsis: bool = False) -> List[str]:
    """Step names for a flag set, in the fixed documentation order."""
    names = {n for bit, n in _FLAG_NAMES if flags & bit}
    if ellipsis:
        names.add("ellipsis")
    return [s for s in STEP_ORDER if s in names]


class Normalized:
    """Normalized text plus the per-character map back to the original text."""

    def __init__(self, raw: str, text: str, ostart: List[int], oend: List[int], rstart: List[int], flags: List[int]):
        self.raw = raw
        self.text = text
        self.ostart = ostart
        self.oend = oend
        self.rstart = rstart
        self.flags = flags

    @property
    def index_map(self) -> List[int]:
        """index_map[i] = original offset of normalized character i."""
        return self.ostart

    def trim(self) -> Tuple[int, int]:
        """Range [a, b) of the normalized text without leading and trailing spaces."""
        a, b = 0, len(self.text)
        while a < b and self.text[a] == " ":
            a += 1
        while b > a and self.text[b - 1] == " ":
            b -= 1
        return a, b

    def span(self, i: int, j: int) -> Tuple[int, int]:
        """Original offsets [start, end) covered by normalized characters i..j-1."""
        return self.ostart[i], self.oend[j - 1]

    def raw_piece(self, i: int) -> str:
        """Raw original text behind normalized character i, including characters removed just before it."""
        return self.raw[self.rstart[i]:self.oend[i]]


def line_starts(text: str) -> List[int]:
    """Offsets where each line of ``text`` starts (line k starts at result[k-1])."""
    starts = [0]
    pos = text.find("\n")
    while pos != -1:
        starts.append(pos + 1)
        pos = text.find("\n", pos + 1)
    return starts


def line_of(starts: List[int], offset: int) -> int:
    """1-based line number of an original offset."""
    return bisect.bisect_right(starts, offset)


def normalize(text: str, join_hyphen: bool = True, cjk_strip: bool = False) -> Normalized:
    """Normalize ``text``.

    ``join_hyphen``: a hyphen at a line end is dropped together with the break (``min-\\nutes`` -> ``minutes``);
    when False the hyphen stays and only the break is dropped (``well-\\nknown`` -> ``well-known``).
    ``cjk_strip``: spaces next to a CJK character are dropped.
    """
    n = len(text)
    out: List[str] = []
    ostart: List[int] = []
    oend: List[int] = []
    rstart: List[int] = []
    flags: List[int] = []
    pend = -1      # original offset where characters removed before the next character begin
    pflag = 0
    i = 0

    def emit(chars: str, s: int, e: int, f: int) -> None:
        nonlocal pend, pflag
        rs = pend if pend >= 0 else s
        f |= pflag
        pend, pflag = -1, 0
        for c in chars:
            out.append(c)
            ostart.append(s)
            oend.append(e)
            rstart.append(rs)
            flags.append(f)
            rs = s
            f = 0

    def drop(s: int, f: int) -> None:
        nonlocal pend, pflag
        if pend < 0:
            pend = s
        pflag |= f

    while i < n:
        m = _PLAIN_RE.match(text, i)
        if m:
            j = m.end()
            if pend >= 0:
                emit(text[i], i, i + 1, 0)
                i += 1
            if j > i:
                run = text[i:j]
                out.extend(run)
                ostart.extend(range(i, j))
                oend.extend(range(i + 1, j + 1))
                rstart.extend(range(i, j))
                flags.extend([0] * (j - i))
            i = j
            continue
        ch = text[i]
        if ch.isspace():
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            run = text[i:j]
            f = WHITESPACE if run != " " else 0
            prev = out[-1] if out else ""
            nxt = text[j] if j < n else ""
            if cjk_strip and ((prev and is_cjk(prev)) or (nxt and is_cjk(nxt))):
                drop(i, CJK_SPACING)
                i = j
                continue
            # Markdown blockquote markers at the start of a following line
            at_line_start = "\n" in run or i == 0
            k = j
            if at_line_start and k < n and text[k] == ">":
                while k < n and (text[k] == ">" or text[k] == " "):
                    k += 1
                f |= MD_MARKUP
                j = k
            if prev == " ":
                drop(i, f)
            else:
                emit(" ", i, j, f)
            i = j
            continue
        if ch == ">" and i == 0:
            k = 1
            while k < n and (text[k] == ">" or text[k] == " "):
                k += 1
            drop(0, MD_MARKUP)
            i = k
            continue
        if ch in HYPHEN_CHARS or ch == "\u00ad":
            if ch == "\u00ad":
                drop(i, DEHYPHEN)
                i += 1
                continue
            j = i + 1
            while j < n and text[j] in " \t":
                j += 1
            if out and out[-1].isalpha() and j < n and text[j] in "\r\n":
                k = j
                while k < n and text[k].isspace():
                    k += 1
                if k < n and text[k].isalpha():
                    if join_hyphen:
                        drop(i, DEHYPHEN)
                    else:
                        emit("-", i, i + 1, DASHES if ch != "-" else 0)
                        drop(i + 1, DEHYPHEN)
                    i = k
                    continue
            emit("-", i, i + 1, DASHES if ch != "-" else 0)
            i += 1
            continue
        if ch in DASH_CHARS:
            emit("-", i, i + 1, DASHES)
            i += 1
            continue
        if ch in QUOTE_MAP:
            emit(QUOTE_MAP[ch], i, i + 1, QUOTES)
            i += 1
            continue
        if ch == "…":
            emit(ch, i, i + 1, 0)
            i += 1
            continue
        if ch == "*" or ch == "`":
            drop(i, MD_MARKUP)
            i += 1
            continue
        if ch in "~_" and text.startswith(ch * 2, i):
            drop(i, MD_MARKUP)
            drop(i + 1, MD_MARKUP)
            i += 2
            continue
        # general character: keep combining marks and conjoining Hangul jamo with their base for NFKC
        j = i + 1
        while j < n and (unicodedata.combining(text[j]) or 0x1160 <= ord(text[j]) <= 0x11FF):
            j += 1
        cluster = text[i:j]
        nf = cluster if cluster.isascii() else unicodedata.normalize("NFKC", cluster)
        f = NFKC if nf != cluster else 0
        lo = nf.lower()
        if lo != nf:
            f |= CASE
        if not lo:
            drop(i, f)
        else:
            emit(lo, i, j, f)
        i = j
    return Normalized(text, "".join(out), ostart, oend, rstart, flags)


def split_ellipsis(quote: str) -> List[str]:
    """Split a quote at ``[...]`` / ``...`` / ``…`` markers into the fragments that must appear in order."""
    parts = [p for p in ELLIPSIS_SPLIT_RE.split(quote) if p.strip()]
    return parts or [quote]


def steps_for_match(qn: Normalized, qi: int, length: int, sn: Normalized, si: int) -> int:
    """Flag set of the steps that mattered while matching ``length`` aligned characters.

    A position counts only when its raw text differs between quote and source, so a capitalised word that
    is spelled the same on both sides does not report ``case``.
    """
    flags = 0
    for k in range(length):
        a, b = qi + k, si + k
        if qn.raw_piece(a) == sn.raw_piece(b):
            continue
        flags |= qn.flags[a] | sn.flags[b]
    return flags
