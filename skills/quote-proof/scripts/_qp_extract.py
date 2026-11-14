"""Find quoted passages and their claimed sources in a Markdown report."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from _qp_normalize import is_cjk
from _qp_sources import clean_path

DEFAULT_MIN_WORDS = 4

_FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
_FOOTDEF_RE = re.compile(r"^ {0,3}\[\^([^\]\s]+)\]:[ \t]*(.*)$")
_FOOTREF_RE = re.compile(r"\[\^([^\]\s]+)\]")
_BLOCK_RE = re.compile(r"^ {0,3}>")
_PARA_BREAK_RE = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)")
_INLINE_QUOTE_RE = re.compile(r'"([^"]+)"|“([^”]+)”|「([^」]+)」|『([^』]+)』')
_CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1", re.S)
_PATH = r"[^\s()\[\]:#<>\"']+"
# (path:12) (path:12-14) (path:p.3) (path:page 3) (path)
_PAREN_RE = re.compile(r"\(\s*(" + _PATH + r")(?::\s*(?:(p\.|page\s+)\s*(\d+)|(\d+)(?:\s*[-–]\s*(\d+))?))?\s*\)")
# [text](path#L12-L20) [text](path)
_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(" + _PATH + r")(?:#L(\d+)(?:\s*-\s*L?(\d+))?)?\s*\)")
# footnote definition body: path:12-14 | path:p.3 | path | [text](path#L3)
_DEF_PATH_RE = re.compile(r"(" + _PATH + r")(?::\s*(?:(p\.|page\s+)\s*(\d+)|(\d+)(?:\s*[-–]\s*(\d+))?))?")


@dataclass
class Claim:
    """Where the report says the quote comes from."""
    path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    page: Optional[int] = None
    style: str = "paren"            # paren | link | footnote
    span: Tuple[int, int] = (0, 0)  # report offsets of the text an anchor fix replaces

    def to_json(self) -> dict:
        return {"path": self.path, "line_start": self.line_start, "line_end": self.line_end, "page": self.page}


@dataclass
class Quote:
    id: int
    report_line: int
    kind: str                       # inline | block
    quote: str
    claim: Optional[Claim]
    span: Tuple[int, int]           # report offsets of the quoted text (without surrounding quote marks)
    fields: Dict[str, object] = field(default_factory=dict)


_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")


def _looks_local(path: str, has_line: bool) -> bool:
    """A local file path: a file extension, or (with a line number) at least a folder separator."""
    if "://" in path or path.startswith(("mailto:", "#")):
        return False
    return bool(_EXT_RE.search(path)) or (has_line and "/" in path)


def _claim_from(m: "re.Match[str]", kind: str, offset: int) -> Optional[Claim]:
    """Claim from a (path:line) group (kind ``paren``) or a Markdown link (kind ``link``)."""
    path = m.group(1)
    if kind == "paren":
        page = int(m.group(3)) if m.group(3) else None
        ls = int(m.group(4)) if m.group(4) else None
        le = int(m.group(5)) if m.group(5) else ls
        text = m.group(0)[1:-1]     # the inside of the parentheses, without the spaces around it
        lead = len(text) - len(text.lstrip())
        span = (offset + m.start() + 1 + lead, offset + m.end() - 1 - (len(text) - len(text.rstrip())))
    else:
        page = None
        ls = int(m.group(2)) if m.group(2) else None
        le = int(m.group(3)) if m.group(3) else ls
        end = m.end(3) if m.group(3) else (m.end(2) if m.group(2) else m.end(1))
        span = (offset + m.start(1), offset + end)
    if not _looks_local(path, ls is not None or page is not None):
        return None
    return Claim(clean_path(path), ls, le, page, kind, span)


def _footnote_defs(lines: List[str], offsets: List[int]) -> Dict[str, Claim]:
    defs: Dict[str, Claim] = {}
    fenced = False
    for ln, line in enumerate(lines):
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = _FOOTDEF_RE.match(line)
        if not m:
            continue
        body_start = m.start(2)
        body = m.group(2)
        lm = _LINK_RE.search(body)
        c = _claim_from(lm, "link", offsets[ln] + body_start) if lm else None
        if c:
            defs[m.group(1)] = c
            continue
        pm = _DEF_PATH_RE.match(body)
        if not pm:
            continue
        page = int(pm.group(3)) if pm.group(3) else None
        ls = int(pm.group(4)) if pm.group(4) else None
        le = int(pm.group(5)) if pm.group(5) else ls
        if _looks_local(pm.group(1), ls is not None or page is not None):
            defs[m.group(1)] = Claim(clean_path(pm.group(1)), ls, le, page, "footnote",
                                     (offsets[ln] + body_start, offsets[ln] + body_start + pm.end()))
    return defs


def _mask_code(text: str) -> str:
    """Blank out code spans (same length, newlines kept) so quotes inside them are ignored."""
    return _CODE_SPAN_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _find_claim(text: str, offset: int, defs: Dict[str, Claim]) -> Optional[Claim]:
    """First anchor in ``text``: a footnote reference, a link or a (path:line) group."""
    best: Optional[Tuple[int, Claim]] = None
    for m in _FOOTREF_RE.finditer(text):
        c = defs.get(m.group(1))
        if c:
            best = (m.start(), c)
            break
    for rx, kind in ((_LINK_RE, "link"), (_PAREN_RE, "paren")):
        for m in rx.finditer(text):
            c = _claim_from(m, kind, offset)
            if c and (best is None or m.start() < best[0]):
                best = (m.start(), c)
                break
    return best[1] if best else None


def _short(quote: str, min_words: int) -> bool:
    """True when the quote is too short to check (emphasis quotes like "safe mode")."""
    letters = [c for c in quote if c.isalnum()]
    cjk = sum(1 for c in letters if is_cjk(c))
    if letters and cjk * 2 >= len(letters):
        return cjk < min_words * 2
    return len(re.findall(r"\w+", quote)) < min_words


def extract(report: str, min_words: int = DEFAULT_MIN_WORDS) -> List[Quote]:
    """All checkable quotes of a Markdown report, in report order."""
    lines = report.split("\n")
    offsets: List[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    defs = _footnote_defs(lines, offsets)

    items: List[Quote] = []
    fenced = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if _FENCE_RE.match(line):
            fenced = not fenced
            i += 1
            continue
        if fenced or _FOOTDEF_RE.match(line):
            i += 1
            continue
        if _BLOCK_RE.match(line):
            j = i
            while j < len(lines) and _BLOCK_RE.match(lines[j]):
                j += 1
            _block(lines, offsets, i, j, defs, min_words, items)
            i = j
            continue
        if not line.strip():
            i += 1
            continue
        j = i + 1     # paragraph: until a blank line or a line that starts a new block
        while (j < len(lines) and lines[j].strip() and not _FENCE_RE.match(lines[j]) and not _FOOTDEF_RE.match(lines[j])
               and not _BLOCK_RE.match(lines[j]) and not _PARA_BREAK_RE.match(lines[j])):
            j += 1
        _paragraph(lines, offsets, i, j, defs, min_words, items)
        i = j
    items.sort(key=lambda q: q.span[0])
    for n, q in enumerate(items, 1):
        q.id = n
    return items


def _block(lines, offsets, i, j, defs, min_words, items) -> None:
    """One blockquote (consecutive ``>`` lines) is one item; short quotes inside are not extracted."""
    contents = []
    starts = []
    for k in range(i, j):
        m = re.match(r"^ {0,3}(?:>[ \t]?)+", lines[k])
        contents.append(lines[k][m.end():])
        starts.append(offsets[k] + m.end())
    last = contents[-1]
    last_off = starts[-1]
    claim: Optional[Claim] = None
    cut = len(last)
    # an anchor at the very end of the last line belongs to the block
    for rx, kind in ((_LINK_RE, "link"), (_PAREN_RE, "paren")):
        ms = list(rx.finditer(last))
        if ms and not last[ms[-1].end():].strip(" .,;:)]—-–"):
            c = _claim_from(ms[-1], kind, last_off)
            if c:
                claim, cut = c, ms[-1].start()
                break
    if claim is None:
        refs = list(_FOOTREF_RE.finditer(last))
        if refs and refs[-1].group(1) in defs and not last[refs[-1].end():].strip(" .,;:)]"):
            claim, cut = defs[refs[-1].group(1)], refs[-1].start()
    last_body = last[:cut].rstrip(" \t—-–")
    body_lines = contents[:-1] + [last_body]
    text = "\n".join(body_lines).strip()
    if not text or _short(text, min_words):
        return
    first_nonblank = next((k for k, c in enumerate(body_lines) if c.strip()), 0)
    start = starts[first_nonblank] + (len(body_lines[first_nonblank]) - len(body_lines[first_nonblank].lstrip()))
    end = last_off + len(last_body)
    items.append(Quote(0, i + 1, "block", text, claim, (start, end)))


def _paragraph(lines, offsets, i, j, defs, min_words, items) -> None:
    start_off = offsets[i]
    para = "\n".join(lines[i:j])
    masked = _mask_code(para)
    matches = list(_INLINE_QUOTE_RE.finditer(masked))
    for idx, m in enumerate(matches):
        g = next(x for x in range(1, 5) if m.group(x) is not None)
        inner_start, inner_end = m.start(g), m.end(g)
        quote = para[inner_start:inner_end].strip()
        lead = len(para[inner_start:inner_end]) - len(para[inner_start:inner_end].lstrip())
        if not quote or _short(quote, min_words):
            continue
        limit = matches[idx + 1].start() if idx + 1 < len(matches) else len(para)
        tail_start = m.end()
        tail = para[tail_start:min(limit, tail_start + 200)]
        claim = _find_claim(tail, start_off + tail_start, defs)
        line = i + 1 + para.count("\n", 0, inner_start + lead)
        s = start_off + inner_start + lead
        items.append(Quote(0, line, "inline", quote, claim, (s, s + len(quote))))
