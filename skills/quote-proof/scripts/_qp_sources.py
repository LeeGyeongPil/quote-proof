"""Source files: one path rule for every path input, reading, HTML text extraction and line/page lookup."""
from __future__ import annotations

import bisect
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from _qp_normalize import Normalized, has_cjk, has_hyphen_break, line_of, line_starts, normalize

MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_DISCOVERED_FILES = 2000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".rst", ".adoc", ".html", ".htm", ".log", ".csv", ".json", ".yaml",
                 ".yml", ".toml", ".ini", ".cfg", ".xml", ".tex", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                 ".java", ".kt", ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sh", ".sql", ".swift", ".dart"}
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer", "h1", "h2",
               "h3", "h4", "h5", "h6", "pre", "blockquote", "hr", "dt", "dd", "title", "body", "head"}
_SKIP_TAGS = {"script", "style"}


# ---------- one path rule for every path input ----------

def clean_path(raw: str) -> str:
    """The single rule applied to every path the user, a report anchor or an option gives.

    Surrounding whitespace is dropped, backslashes become slashes, ``./`` prefixes and duplicate slashes go away
    and ``a/../b`` is collapsed. Relative paths stay relative, absolute paths stay absolute.
    """
    p = raw.strip().replace("\\", "/")
    absolute = p.startswith("/")
    parts: List[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == ".." and parts and parts[-1] != "..":
            parts.pop()
            continue
        if seg == ".." and absolute:
            continue
        parts.append(seg)
    joined = "/".join(parts)
    return ("/" + joined) if absolute else (joined or ".")


def resolve_inside(root: Path, raw: str) -> Optional[Tuple[str, Path]]:
    """Resolve a path against ``root``. Returns (display path relative to root, absolute path) or None when
    the path leaves the root (``..`` or a symlink pointing outside)."""
    cleaned = clean_path(raw)
    root_abs = root.resolve()
    target = Path(cleaned) if cleaned.startswith("/") else root_abs / cleaned
    try:
        real = target.resolve()
        rel = real.relative_to(root_abs)
    except (ValueError, OSError, RuntimeError):
        return None
    return rel.as_posix(), real


# ---------- source text ----------

class SourceText:
    """A decoded source file with offset -> line / page lookup and cached normalized variants."""

    def __init__(self, path: str, text: str, marks: Optional[List[Tuple[int, int]]] = None):
        self.path = path
        self.text = text
        if marks is None:
            self._starts = line_starts(text)
            self._mark_offsets = None
            self._mark_lines = None
        else:
            self._starts = None
            self._mark_offsets = [m[0] for m in marks]
            self._mark_lines = [m[1] for m in marks]
        self._form_feeds = [i for i, c in enumerate(text) if c == "\f"] if "\f" in text else []
        self._variants: Dict[Tuple[bool, bool], Normalized] = {}
        self._extra: Dict[tuple, object] = {}
        self.has_cjk = has_cjk(text)
        self.has_hyphen_break = has_hyphen_break(text)

    def line_at(self, offset: int) -> int:
        """Line in the original file (for HTML: the line of the markup the text came from)."""
        if self._starts is not None:
            return line_of(self._starts, offset)
        k = bisect.bisect_right(self._mark_offsets, offset) - 1
        return self._mark_lines[max(k, 0)] if self._mark_lines else 1

    def page_at(self, offset: int) -> int:
        """1-based page for text split by form feeds (pdftotext style)."""
        return bisect.bisect_right(self._form_feeds, offset) + 1

    def variant(self, join_hyphen: bool, cjk_strip: bool) -> Normalized:
        key = (join_hyphen, cjk_strip)
        if key not in self._variants:
            self._variants[key] = normalize(self.text, join_hyphen, cjk_strip)
        return self._variants[key]

    def cache(self, key: tuple, make: Callable[[], object]) -> object:
        """Per-source cache for alignment helpers (token lists, n-gram indexes)."""
        if key not in self._extra:
            self._extra[key] = make()
        return self._extra[key]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.marks: List[Tuple[int, int]] = [(0, 1)]
        self.length = 0
        self._skip = 0

    def _add(self, text: str, line: int) -> None:
        self.marks.append((self.length, line))
        for k, c in enumerate(text):
            if c == "\n":
                line += 1
                self.marks.append((self.length + k + 1, line))
        self.parts.append(text)
        self.length += len(text)

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._add("\n", self.getpos()[0])

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self._add("\n", self.getpos()[0])

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self._add("\n", self.getpos()[0])

    def handle_data(self, data):
        if not self._skip:
            self._add(data, self.getpos()[0])


def html_to_source(path: str, html: str) -> SourceText:
    """Text of an HTML file; every fragment remembers the line of the markup it came from."""
    ex = _TextExtractor()
    ex.feed(html)
    ex.close()
    return SourceText(path, "".join(ex.parts), ex.marks)


class SourceError(Exception):
    """A source could not be used. ``code`` is ``unreadable``, ``too_large`` or ``outside_root``."""

    def __init__(self, code: str, path: str):
        super().__init__(f"{code}: {path}")
        self.code = code
        self.path = path


def read_source(display: str, real: Path) -> SourceText:
    try:
        size = real.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise SourceError("too_large", display)
        data = real.read_bytes()
    except OSError:
        raise SourceError("unreadable", display) from None
    if b"\x00" in data:
        raise SourceError("unreadable", display)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceError("unreadable", display) from None
    if real.suffix.lower() in (".html", ".htm"):
        return html_to_source(display, text)
    return SourceText(display, text)


class SourceStore:
    """Finds and caches the source files of one run. Problems are collected in ``warnings`` as (code, path)."""

    def __init__(self, root: Path, report_real: Optional[Path], explicit: List[str], report_text: str = ""):
        self.root = root
        self.report_real = report_real
        # lines of the report: a discovered file that repeats most of them is a copy of the report, not a source
        lines = {ln.strip() for ln in report_text.splitlines() if len(ln.strip()) >= 12}
        self._report_lines = lines if len(lines) >= 2 else set()
        self.warnings: List[Tuple[str, str]] = []
        self._cache: Dict[str, Optional[SourceText]] = {}
        self._warned: set = set()
        self.explicit: List[str] = []
        for raw in explicit:
            r = resolve_inside(root, raw)
            if r is None:
                self._warn("outside_root", clean_path(raw))
            elif r[0] not in self.explicit:
                self.explicit.append(r[0])
        self._discovered: Optional[List[str]] = None

    def _warn(self, code: str, path: str) -> None:
        if (code, path) not in self._warned:
            self._warned.add((code, path))
            self.warnings.append((code, path))

    def get(self, raw: str, quiet: bool = False) -> Optional[SourceText]:
        """Source by path (any path rule input). None when it cannot be used (a warning is recorded)."""
        r = resolve_inside(self.root, raw)
        if r is None:
            if not quiet:
                self._warn("outside_root", clean_path(raw))
            return None
        display, real = r
        if display in self._cache:
            return self._cache[display]
        if not real.is_file():
            self._cache[display] = None
            return None
        try:
            src = read_source(display, real)
        except SourceError as e:
            if not quiet:
                self._warn(e.code, display)
            self._cache[display] = None
            return None
        self._cache[display] = src
        return src

    def exists(self, raw: str) -> bool:
        r = resolve_inside(self.root, raw)
        return r is not None and r[1].is_file()

    def candidates(self) -> List[str]:
        """Files to search when a quote has no anchor: --source files, else the text files under the root."""
        if self.explicit:
            return list(self.explicit)
        if self._discovered is None:
            found: List[str] = []
            root_abs = self.root.resolve()
            for dirpath, dirnames, filenames in os.walk(root_abs):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
                for name in sorted(filenames):
                    if name.startswith(".") or Path(name).suffix.lower() not in TEXT_SUFFIXES:
                        continue
                    full = Path(dirpath) / name
                    if self.report_real is not None and full.resolve() == self.report_real:
                        continue
                    found.append(full.relative_to(root_abs).as_posix())
                    if len(found) >= MAX_DISCOVERED_FILES:
                        break
                if len(found) >= MAX_DISCOVERED_FILES:
                    break
            self._discovered = sorted(p for p in found if not self._is_report_copy(p))
        return self._discovered

    def _is_report_copy(self, path: str) -> bool:
        """True when the file shares at least half of the report's lines (a fixed copy, an older draft)."""
        if not self._report_lines:
            return False
        src = self.get(path, quiet=True)
        if src is None:
            return False
        lines = {ln.strip() for ln in src.text.splitlines()}
        return len(self._report_lines & lines) * 2 >= len(self._report_lines)
