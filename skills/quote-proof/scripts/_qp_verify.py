"""Verdicts for every quote of a report, fix suggestions and the corrected copy."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from _qp_align import Match, clean_slice, find_approximate, find_exact, find_normalized
from _qp_extract import Claim, Quote
from _qp_sources import SourceStore, SourceText

VERDICTS = ("exact", "normalized", "approximate", "not_found", "source_missing")


@dataclass
class Result:
    quote: Quote
    verdict: str
    match: Optional[Match] = None
    found_path: Optional[str] = None
    anchor: str = "none"                 # ok | wrong_line | wrong_file | none
    best_ratio: Optional[float] = None
    also_in: List[str] = field(default_factory=list)
    missing_path: Optional[str] = None   # the claimed source that could not be read
    suggestion: Optional[Dict[str, Optional[str]]] = None
    fix_anchor: Optional[Tuple[Tuple[int, int], str]] = None   # report span and replacement text of the anchor

    @property
    def steps(self) -> List[str]:
        return self.match.steps if self.match else []


def _overlaps(claim: Claim, m: Match) -> bool:
    if claim.page is not None:
        return m.page_start <= claim.page <= m.page_end
    if claim.line_start is None:
        return True
    return m.line_start <= (claim.line_end or claim.line_start) and claim.line_start <= m.line_end


def _pick(matches: List[Match], claim: Optional[Claim], same_file: bool) -> Match:
    """Among several occurrences prefer the one the anchor points at."""
    if claim is not None and same_file:
        for m in matches:
            if _overlaps(claim, m):
                return m
    return matches[0]


def _locate_verbatim(quote: str, src: SourceText) -> List[Match]:
    return find_exact(quote, src) or find_normalized(quote, src)


def _anchor_state(claim: Optional[Claim], path: str, m: Match) -> str:
    if claim is None:
        return "none"
    if claim.path != path:
        return "wrong_file"
    return "ok" if _overlaps(claim, m) else "wrong_line"


def _line_text(a: int, b: int) -> str:
    return str(a) if a == b else f"{a}-{b}"


def anchor_text(path: str, m: Match, claim: Claim) -> Tuple[str, str]:
    """(display anchor, replacement text in the claim's own syntax) for the place where the quote was found."""
    if claim.page is not None:
        loc = f"p.{m.page_start}"
        return f"{path}:{loc}", f"{path}:{loc}"
    lines = _line_text(m.line_start, m.line_end)
    display = f"{path}:{lines}"
    if claim.style == "link":
        frag = f"#L{m.line_start}" if m.line_start == m.line_end else f"#L{m.line_start}-L{m.line_end}"
        return display, f"{path}{frag}"
    return display, display


def claim_text(claim: Claim) -> str:
    if claim.page is not None:
        return f"{claim.path}:p.{claim.page}"
    if claim.line_start is None:
        return claim.path
    return f"{claim.path}:{_line_text(claim.line_start, claim.line_end or claim.line_start)}"


def _finish(res: Result) -> Result:
    """Fill the suggestion of an approximate quote or a wrong anchor."""
    q, m, claim = res.quote, res.match, res.quote.claim
    if m is None or res.verdict in ("not_found", "source_missing"):
        return res
    replace_quote = clean_slice(m.text) if res.verdict == "approximate" else None
    anchor = None
    if res.anchor in ("wrong_line", "wrong_file") and claim is not None and res.found_path:
        path = claim.path if claim.path == res.found_path else res.found_path
        shown, repl = anchor_text(path, m, claim)
        anchor = shown
        res.fix_anchor = (claim.span, repl)
    if replace_quote is not None or anchor is not None:
        res.suggestion = {"replace_quote": replace_quote, "anchor": anchor}
    return res


def verify_item(item: Quote, store: SourceStore, min_ratio: float) -> Result:
    claim = item.claim
    quote = item.quote
    if claim is not None:
        src = store.get(claim.path)
        if src is None:
            return Result(item, "source_missing", missing_path=claim.path)
        matches = _locate_verbatim(quote, src)
        if matches:
            m = _pick(matches, claim, True)
            return _finish(Result(item, m.verdict, m, src.path, _anchor_state(claim, src.path, m)))
        approx, best = find_approximate(quote, src, min_ratio)
        if approx is not None:
            return _finish(Result(item, "approximate", approx, src.path, _anchor_state(claim, src.path, approx),
                                  best_ratio=best))
        for other_path in store.candidates():
            if other_path == src.path:
                continue
            other = store.get(other_path, quiet=True)
            if other is None:
                continue
            matches = _locate_verbatim(quote, other)
            if matches:
                m = matches[0]
                return _finish(Result(item, m.verdict, m, other.path, "wrong_file"))
        return Result(item, "not_found", best_ratio=best)
    # no anchor: search the --source files, or every text file under the root
    sources = [s for s in (store.get(p, quiet=True) for p in store.candidates()) if s is not None]
    if not sources:
        return Result(item, "source_missing")
    hits: List[Tuple[SourceText, List[Match]]] = []
    for src in sources:
        ms = _locate_verbatim(quote, src)
        if ms:
            hits.append((src, ms))
    if hits:
        src, ms = hits[0]
        return _finish(Result(item, ms[0].verdict, ms[0], src.path, "none", also_in=[s.path for s, _ in hits[1:]]))
    best_overall: Optional[Tuple[float, SourceText, Match]] = None
    best_ratio: Optional[float] = None
    for src in sources:
        approx, ratio = find_approximate(quote, src, min_ratio)
        if ratio is not None and (best_ratio is None or ratio > best_ratio):
            best_ratio = ratio
        if approx is not None and (best_overall is None or (approx.ratio or 0) > best_overall[0]):
            best_overall = (approx.ratio or 0, src, approx)
    if best_overall is not None:
        _, src, m = best_overall
        return _finish(Result(item, m.verdict, m, src.path, "none", best_ratio=best_ratio))
    return Result(item, "not_found", best_ratio=best_ratio)


def verify_all(items: List[Quote], store: SourceStore, min_ratio: float) -> List[Result]:
    return [verify_item(i, store, min_ratio) for i in items]


def summarize(results: List[Result]) -> Dict[str, int]:
    s = {v: 0 for v in VERDICTS}
    s["anchor_wrong"] = 0
    for r in results:
        s[r.verdict] += 1
        if r.anchor in ("wrong_line", "wrong_file"):
            s["anchor_wrong"] += 1
    return s


def summary_line(s: Dict[str, int]) -> str:
    return ("SUMMARY exact={exact} normalized={normalized} approximate={approximate} not_found={not_found} "
            "source_missing={source_missing} anchor_wrong={anchor_wrong}").format(**s)


def exit_code(s: Dict[str, int]) -> int:
    """0 clean, 1 approximate or wrong anchors, 2 not found or missing source."""
    if s["not_found"] or s["source_missing"]:
        return 2
    if s["approximate"] or s["anchor_wrong"]:
        return 1
    return 0


def apply_fixes(report: str, results: List[Result]) -> Tuple[str, int, int]:
    """Copy of the report with approximate quotes replaced by the source text and wrong anchors corrected.
    Returns (text, quote fixes, anchor fixes). Quotes that were not found are left alone."""
    edits: List[Tuple[int, int, str, str]] = []
    for r in results:
        if r.suggestion and r.suggestion.get("replace_quote"):
            new = r.suggestion["replace_quote"] or ""
            s, e = r.quote.span
            if r.quote.kind == "inline" and s > 0 and report[s - 1] == '"' and '"' in new:
                parts = new.split('"')
                new = "".join(p + ("“" if i % 2 == 0 else "”") for i, p in enumerate(parts[:-1])) + parts[-1]
            edits.append((s, e, new, "quote"))
        if r.fix_anchor is not None:
            (s, e), new = r.fix_anchor
            edits.append((s, e, new, "anchor"))
    edits.sort(key=lambda x: (x[0], x[1]))
    applied: List[Tuple[int, int, str, str]] = []
    for ed in edits:
        if any(ed[0] < a[1] and a[0] < ed[1] or (ed[0], ed[1]) == (a[0], a[1]) for a in applied):
            continue
        applied.append(ed)
    out = report
    for s, e, new, _ in sorted(applied, key=lambda x: -x[0]):
        out = out[:s] + new + out[e:]
    return out, sum(1 for a in applied if a[3] == "quote"), sum(1 for a in applied if a[3] == "anchor")
