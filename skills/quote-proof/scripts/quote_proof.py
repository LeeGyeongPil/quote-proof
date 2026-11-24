#!/usr/bin/env python3
"""quote-proof: check the quotes and source anchors of a Markdown report against local source files.

    quote_proof.py extract REPORT.md
    quote_proof.py verify  [REPORT.md] [--root DIR] [--source FILE ...] [--json] [--out FILE] [--fix] [--write FIXED.md]
    quote_proof.py suggest [REPORT.md] [--root DIR] [--write FIXED.md]

Without REPORT.md, verify and suggest use the only Markdown file under --root whose quotes cite a source.
verify --fix checks the report, writes the corrected copy REPORT.fixed.md, lists what is left to fix by hand and
re-checks the copy in one run (the exit code is the copy's).

Verdicts: exact, normalized (differences in line breaks, hyphenation, quotes, ... are listed), approximate
(closest passage with a similarity ratio), not_found, source_missing. Anchors: ok, wrong_line, wrong_file, none.
Exit codes: 0 clean, 1 approximate or wrong anchors, 2 not_found or source_missing, 3 usage or input error.
Standard library only, Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))   # work even when Python does not add the script folder

import _qp_i18n as i18n  # noqa: E402
from _qp_extract import DEFAULT_MIN_WORDS, extract  # noqa: E402
from _qp_sources import MAX_DISCOVERED_FILES, MAX_SOURCE_BYTES, SKIP_DIRS, SourceStore, clean_path  # noqa: E402
from _qp_verify import (Result, anchor_text, apply_fixes, claim_text, exit_code, summarize, summary_line,  # noqa: E402
                        verify_all)

__version__ = "0.1.4"
EXIT_USAGE = 3
DEFAULT_MIN_RATIO = 0.8
REPORT_SUFFIXES = (".md", ".markdown")


class UsageError(Exception):
    """A user-facing error: ``key`` is a message key, ``params`` fill its placeholders."""

    def __init__(self, key: str, **params: object):
        super().__init__(key)
        self.key = key
        self.params = params


# ---------- table helpers ----------

def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _table(headers: List[str], rows: List[List[str]]) -> str:
    widths = [max([_width(h)] + [_width(r[i]) for r in rows]) for i, h in enumerate(headers)]

    def line(cells: List[str]) -> str:
        return "  ".join(c + " " * (widths[i] - _width(c)) for i, c in enumerate(cells)).rstrip()

    return "\n".join([line(headers)] + [line(r) for r in rows])


# ---------- language and arguments ----------

def _prescan_lang(argv: Sequence[str]) -> Optional[str]:
    """The raw --lang value anywhere in the arguments (the last one wins), so help and errors use it."""
    value: Optional[str] = None
    args = list(argv)
    for k, a in enumerate(args):
        if a == "--":
            break
        if a == "--lang" and k + 1 < len(args):
            value = args[k + 1]
        elif a.startswith("--lang="):
            value = a.split("=", 1)[1]
    return value


def build_parser(lang: str) -> argparse.ArgumentParser:
    T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731 - short local alias

    class Formatter(argparse.HelpFormatter):
        def add_usage(self, usage, actions, groups, prefix=None):
            # argparse passes prefix='' when it builds the program name of a subcommand: keep that
            super().add_usage(usage, actions, groups, prefix=T("usage_prefix") if prefix is None else prefix)

    class Parser(argparse.ArgumentParser):
        def error(self, message):   # usage errors exit 3 so they never look like a verdict (1 and 2)
            sys.stderr.write(i18n.error_text(lang, "err_usage", detail=message) + "\n")
            raise SystemExit(EXIT_USAGE)

    def style(p: argparse.ArgumentParser) -> None:
        """Localized section titles and -h (argparse's own English words are replaced)."""
        p._positionals.title = T("help_title_positional")
        p._optionals.title = T("help_title_options")
        p.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help=T("help_h"))

    def lang_option(p: argparse.ArgumentParser) -> None:
        p.add_argument("--lang", default=argparse.SUPPRESS, metavar="en|ko", help=T("help_lang"))

    parser = Parser(prog="quote_proof.py", formatter_class=Formatter, add_help=False, allow_abbrev=False,
                    description=T("help_main"), epilog=T("help_epilog"))
    style(parser)
    lang_option(parser)
    sub = parser.add_subparsers(dest="command", required=True, title=T("help_title_commands"), metavar=T("help_command"))
    for name in ("extract", "verify", "suggest"):
        sp = sub.add_parser(name, help=T("help_" + name), description=T("help_" + name), formatter_class=Formatter,
                            add_help=False, allow_abbrev=False)
        style(sp)
        if name == "extract":
            sp.add_argument("report", help=T("help_report"))
        else:   # verify and suggest can find the report themselves (one less step for an agent)
            sp.add_argument("report", nargs="?", default=None, help=T("help_report_optional"))
        lang_option(sp)
        sp.add_argument("--min-words", default=str(DEFAULT_MIN_WORDS), metavar="N", help=T("help_min_words"))
        if name != "extract":
            sp.add_argument("--root", default=".", metavar="DIR", help=T("help_root"))
            sp.add_argument("--source", action="append", default=[], metavar="FILE", help=T("help_source"))
            sp.add_argument("--min-ratio", default=str(DEFAULT_MIN_RATIO), metavar="R", help=T("help_min_ratio"))
        sp.add_argument("--json", action="store_true", help=T("help_json"))
        if name == "verify":
            sp.add_argument("--out", metavar="FILE", help=T("help_out"))
            # --fix: check, write the corrected copy REPORT.fixed.md and re-check it, all in one run
            sp.add_argument("--fix", action="store_true", help=T("help_fix"))
        if name == "suggest":
            sp.add_argument("--write", metavar="FILE", help=T("help_write"))
        elif name == "verify":
            sp.add_argument("--write", metavar="FILE", help=T("help_fix_write"))
    return parser


# ---------- input checks ----------

def _check_numbers(args) -> tuple:
    try:
        words = int(str(args.min_words).strip())
        if words < 1:
            raise ValueError
    except ValueError:
        raise UsageError("err_min_words", value=args.min_words) from None
    ratio = DEFAULT_MIN_RATIO
    if hasattr(args, "min_ratio"):
        try:
            ratio = float(str(args.min_ratio).strip())
            if not 0.0 <= ratio <= 1.0 or ratio != ratio:
                raise ValueError
        except ValueError:
            raise UsageError("err_min_ratio", value=args.min_ratio) from None
    return words, ratio


def _read_report(raw: str) -> tuple:
    path = Path(clean_path(raw))
    shown = clean_path(raw)
    if not path.is_file():
        raise UsageError("err_report_missing", path=shown)
    try:
        data = path.read_bytes()
    except OSError:
        raise UsageError("err_report_unreadable", path=shown) from None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UsageError("err_report_not_utf8", path=shown) from None
    return shown, path, text


def _find_reports(root: Path, min_words: int) -> List[str]:
    """Markdown files under ``root`` that contain at least one quote with a source anchor (a report, not a source).

    Corrected copies (``*.fixed.md``) are skipped so that a fixed copy and its report do not compete.
    """
    found: List[str] = []
    root_abs = root.resolve()
    looked = 0
    for dirpath, dirnames, filenames in os.walk(root_abs):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if name.startswith(".") or full.suffix.lower() not in REPORT_SUFFIXES or ".fixed." in name:
                continue
            looked += 1
            if looked > MAX_DISCOVERED_FILES:
                return sorted(found)
            try:
                if full.stat().st_size > MAX_SOURCE_BYTES:
                    continue
                text = full.read_bytes().decode("utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            if any(q.claim is not None for q in extract(text, min_words)):
                found.append(clean_path(str(root / full.relative_to(root_abs))))
    return sorted(found)


def _pick_report(raw: Optional[str], root: Path, root_shown: str, min_words: int, lang: str) -> str:
    """The report path given by the user, or the only report under --root (an error names what to do otherwise)."""
    if raw is not None:
        return raw
    found = _find_reports(root, min_words)
    if not found:
        raise UsageError("err_no_report", root=root_shown)
    if len(found) > 1:
        shown = ", ".join(found[:10]) + (", ..." if len(found) > 10 else "")
        raise UsageError("err_many_reports", root=root_shown, paths=shown)
    # stderr, so the table and the SUMMARY line on stdout stay the same as with an explicit report
    sys.stderr.write(i18n.t(lang, "picked_report", path=found[0]) + "\n")
    return found[0]


def _fixed_name(report: Path) -> Path:
    """REPORT.md -> REPORT.fixed.md next to the report."""
    return report.with_name(report.stem + ".fixed" + (report.suffix or ".md"))


def _refuse_report_path(report: Path, other: Optional[str], key: str) -> Optional[Path]:
    """The output path (same path rule as every input); refused when it is the report itself."""
    if other is None:
        return None
    target = Path(clean_path(other))
    if target.resolve() == report.resolve():
        raise UsageError(key)
    return target


def _write_file(path: Path, text: str) -> None:
    try:
        path.write_bytes(text.encode("utf-8"))
    except OSError:
        raise UsageError("err_write_failed", path=clean_path(str(path))) from None


# ---------- rendering ----------

def _found_label(r: Result) -> str:
    m = r.match
    if m is None or r.found_path is None:
        return "-"
    lines = str(m.line_start) if m.line_start == m.line_end else f"{m.line_start}-{m.line_end}"
    return f"{r.found_path}:{lines}"


def _notes(lang: str, r: Result) -> str:
    T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731
    out: List[str] = []
    m = r.match
    if r.verdict == "normalized" and m and m.steps:
        out.append(T("note_steps", steps=", ".join(m.steps)))
    if r.verdict == "approximate" and m:
        out.append(T("note_ratio", ratio=f"{m.ratio:.3f}", changed=m.changed_units,
                     unit=T("unit_char" if m.unit == "char" else "unit_word")))
    if r.verdict == "not_found" and r.best_ratio is not None:
        out.append(T("note_best_ratio", ratio=f"{r.best_ratio:.3f}"))
    claim = r.quote.claim
    if r.anchor in ("wrong_line", "wrong_file") and claim is not None:
        out.append(T("note_claimed_found", claimed=claim_text(claim), found=_found_label(r)))
    if r.verdict == "source_missing" and r.missing_path:
        out.append(T("note_file_missing", path=r.missing_path))
    if r.also_in:
        out.append(T("note_also_in", paths=", ".join(r.also_in)))
    return "; ".join(out)


def _item_json(r: Result) -> dict:
    q, m, claim = r.quote, r.match, r.quote.claim
    return {
        "id": q.id,
        "report_line": q.report_line,
        "kind": q.kind,
        "quote": q.quote,
        "claimed": claim.to_json() if claim else None,
        "verdict": r.verdict,
        "steps": list(m.steps) if m else [],
        "ratio": (m.ratio if m else r.best_ratio),
        "changed_units": m.changed_units if m else None,
        "unit": m.unit if m else None,
        "found": ({"path": r.found_path, "line_start": m.line_start, "line_end": m.line_end,
                   "page_start": m.page_start, "page_end": m.page_end, "text": m.text} if m else None),
        "anchor": r.anchor,
        "also_in": list(r.also_in),
        "suggestion": r.suggestion,
    }


def _verify_json(report: str, root: str, results: List[Result], warnings: List[dict]) -> dict:
    return {"tool": "quote-proof", "version": __version__, "report": report, "root": root,
            "summary": summarize(results), "items": [_item_json(r) for r in results], "warnings": warnings}


def _verify_table(lang: str, results: List[Result]) -> str:
    T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731
    if not results:
        return T("no_quotes")
    headers = [T("col_id"), T("col_line"), T("col_form"), T("col_verdict"), T("col_source"), T("col_anchor"), T("col_note")]
    rows = [[str(r.quote.id), str(r.quote.report_line), r.quote.kind, r.verdict, _found_label(r), r.anchor,
             _notes(lang, r)] for r in results]
    return _table(headers, rows)


def _warning_lines(lang: str, store: SourceStore, echo: bool = True) -> List[dict]:
    keys = {"unreadable": "warn_unreadable", "too_large": "warn_too_large", "outside_root": "warn_outside_root"}
    out = []
    for code, path in store.warnings:
        if echo:   # the re-check of a --fix copy reads the same sources: do not repeat the warnings
            sys.stderr.write(i18n.warning_text(lang, keys[code], path=path) + "\n")
        out.append({"code": code, "path": path})
    return out


# ---------- commands ----------

def _cmd_extract(args, lang: str) -> int:
    words, _ = _check_numbers(args)
    shown, _path, text = _read_report(args.report)
    items = extract(text, words)
    if args.json:
        data = {"tool": "quote-proof", "version": __version__, "report": shown,
                "items": [{"id": q.id, "report_line": q.report_line, "kind": q.kind, "quote": q.quote,
                           "claimed": q.claim.to_json() if q.claim else None} for q in items]}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731
    if not items:
        print(T("no_quotes"))
        return 0
    rows = []
    for q in items:
        quote = q.quote.replace("\n", " ")
        rows.append([str(q.id), str(q.report_line), q.kind, claim_text(q.claim) if q.claim else "-",
                     quote if len(quote) <= 60 else quote[:57] + "..."])
    print(_table([T("col_id"), T("col_line"), T("col_form"), T("col_claimed"), T("col_quote")], rows))
    return 0


@dataclass
class Run:
    """One checked report: the inputs as shown to the user, the verdicts and the output paths."""
    shown: str
    path: Path
    text: str
    root: Path
    root_shown: str
    words: int
    ratio: float
    results: List[Result]
    warnings: List[dict]
    out_path: Optional[Path]
    write_path: Optional[Path]


def _check(path: Path, text: str, root: Path, sources: List[str], words: int, ratio: float, lang: str,
           echo_warnings: bool = True):
    """Extract the quotes of ``text`` (the report at ``path``) and verify each one against the sources."""
    items = extract(text, words)
    store = SourceStore(root, path.resolve(), sources, text)
    results = verify_all(items, store, ratio)
    warnings = _warning_lines(lang, store, echo_warnings)
    return results, warnings


def _run_verify(args, lang: str) -> Run:
    words, ratio = _check_numbers(args)
    root_shown = clean_path(args.root)
    root = Path(root_shown)
    if not root.is_dir():
        raise UsageError("err_root_not_dir", path=root_shown)
    # no REPORT argument: use the only Markdown file under --root that cites sources
    raw = _pick_report(args.report, root, root_shown, words, lang)
    shown, path, text = _read_report(raw)
    out_path = _refuse_report_path(path, getattr(args, "out", None), "err_out_overwrite")
    write_raw = getattr(args, "write", None)
    if write_raw is None and getattr(args, "fix", False):
        write_raw = str(_fixed_name(path))      # verify --fix: REPORT.fixed.md next to the report
    write_path = _refuse_report_path(path, write_raw, "err_write_overwrite")
    results, warnings = _check(path, text, root, list(args.source), words, ratio, lang)
    return Run(shown, path, text, root, root_shown, words, ratio, results, warnings, out_path, write_path)


def _suggestion_lines(lang: str, results: List[Result]) -> List[str]:
    """For each fixable quote: the corrected anchor and/or the exact source text."""
    T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731
    fixable = [r for r in results if r.suggestion]
    if not fixable:
        return [T("no_suggestions")]
    lines: List[str] = []
    for r in fixable:
        lines.append(f"#{r.quote.id} ({T('col_line')} {r.quote.report_line}) {r.verdict} {r.anchor}")
        sg = r.suggestion or {}
        claim = r.quote.claim
        if sg.get("anchor") and claim is not None:
            lines.append("  " + T("sg_anchor", old=claim_text(claim), new=sg["anchor"]))
        if sg.get("replace_quote"):
            lines.append("  " + T("sg_quote"))
            lines.append(f"  > {sg['replace_quote']}")
            lines.append("  " + T("sg_source", where=_found_label(r)))
    return lines


def _suggest_line(s: Dict[str, int], quote_fixes: int, anchor_fixes: int) -> str:
    return f"SUGGEST quote_fixes={quote_fixes} anchor_fixes={anchor_fixes} unfixable={s['not_found'] + s['source_missing']}"


def _todo_lines(lang: str, results: List[Result], copy_shown: str) -> List[str]:
    """What the script cannot fix, with the one action to take for each item (left for the agent or a person)."""
    T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731
    todo: List[str] = []
    for r in results:
        where = f"#{r.quote.id} ({T('col_line')} {r.quote.report_line})"
        if r.verdict == "not_found":
            todo.append("  " + T("todo_not_found", where=where))
        elif r.verdict == "source_missing":
            todo.append("  " + T("todo_source_missing", where=where, path=r.missing_path or "-"))
    return [T("todo_header", path=copy_shown)] + todo if todo else []


def _warn_overwrite(lang: str, path: Path) -> None:
    """One stderr line when a corrected copy replaces an existing file."""
    if path.exists():
        sys.stderr.write(i18n.warning_text(lang, "warn_overwrite", path=clean_path(str(path))) + "\n")


def _cmd_verify(args, lang: str) -> int:
    run = _run_verify(args, lang)
    s = summarize(run.results)
    final = s
    if run.write_path is None:
        # plain check: the table (or JSON) and the SUMMARY line
        if args.json:
            body = json.dumps(_verify_json(run.shown, run.root_shown, run.results, run.warnings),
                              ensure_ascii=False, indent=2)
            screen = [body]
        else:
            body = _verify_table(lang, run.results)
            screen = [body, summary_line(s)]
    else:
        # --fix: check, write the corrected copy, then re-check the copy - one run gives verdicts and fixes
        fixed, quote_fixes, anchor_fixes = apply_fixes(run.text, run.results)
        _warn_overwrite(lang, run.write_path)
        _write_file(run.write_path, fixed)
        copy_shown = clean_path(str(run.write_path))
        after, after_warnings = _check(run.write_path, fixed, run.root, list(args.source), run.words, run.ratio, lang,
                                       echo_warnings=False)
        final = summarize(after)
        if args.json:
            data = _verify_json(run.shown, run.root_shown, run.results, run.warnings)
            data["copy"] = copy_shown
            data["fixes"] = {"quote": quote_fixes, "anchor": anchor_fixes}
            data["after"] = _verify_json(copy_shown, run.root_shown, after, after_warnings)
            body = json.dumps(data, ensure_ascii=False, indent=2)
            screen = [body]
        else:
            T = lambda key, **kw: i18n.t(lang, key, **kw)  # noqa: E731
            lines = [_verify_table(lang, run.results), summary_line(s), ""]
            lines += _suggestion_lines(lang, run.results)
            lines += [T("wrote_copy", path=copy_shown), _suggest_line(s, quote_fixes, anchor_fixes)]
            lines += _todo_lines(lang, after, copy_shown)
            lines += ["", T("fix_recheck", path=copy_shown), _verify_table(lang, after)]
            body = "\n".join(lines)
            screen = [body, summary_line(final)]   # the last line is the SUMMARY of the corrected copy
    if run.out_path is not None:
        _write_file(run.out_path, body + "\n")
        print(i18n.t(lang, "wrote_out", path=clean_path(str(run.out_path))))
        print(summary_line(final))
    else:
        print("\n".join(screen))
    return exit_code(final)


def _cmd_suggest(args, lang: str) -> int:
    run = _run_verify(args, lang)
    s = summarize(run.results)
    fixed, quote_fixes, anchor_fixes = apply_fixes(run.text, run.results)
    if run.write_path is not None:
        _warn_overwrite(lang, run.write_path)
        _write_file(run.write_path, fixed)
    if args.json:
        data = _verify_json(run.shown, run.root_shown, run.results, run.warnings)
        data["copy"] = clean_path(str(run.write_path)) if run.write_path is not None else None
        data["fixes"] = {"quote": quote_fixes, "anchor": anchor_fixes}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    lines = _suggestion_lines(lang, run.results)
    if run.write_path is not None:
        lines.append(i18n.t(lang, "wrote_copy", path=clean_path(str(run.write_path))))
    lines.append(_suggest_line(s, quote_fixes, anchor_fixes))
    print("\n".join(lines))
    return 0


COMMANDS = {"extract": _cmd_extract, "verify": _cmd_verify, "suggest": _cmd_suggest}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    raw_lang = _prescan_lang(args_in)
    if raw_lang is not None and raw_lang.strip().lower() not in i18n.LANGS:
        sys.stderr.write(i18n.error_text(i18n.lang_from_env(), "err_lang", value=raw_lang) + "\n")
        return EXIT_USAGE
    lang = i18n.resolve_lang(raw_lang)
    try:
        args = build_parser(lang).parse_args(args_in)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        return COMMANDS[args.command](args, lang)
    except UsageError as e:
        sys.stderr.write(i18n.error_text(lang, e.key, **e.params) + "\n")
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
