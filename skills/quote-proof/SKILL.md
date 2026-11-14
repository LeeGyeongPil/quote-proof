---
name: quote-proof
description: Verifies that every quoted passage in a Markdown report, summary, answer or design note really appears in the local source files it cites, and that its path:line, footnote or line anchor (path#L12 style) points at the right place. A bundled script normalizes line breaks, hyphenated line ends, curly quotes and CJK spacing, labels each quote exact, normalized, approximate, not_found or source_missing, flags wrong_line and wrong_file anchors, and suggests the exact source text and corrected anchor. Use when the user asks to check, proofread or fact-check quotes, citations or line references in a report, release notes or design doc against docs, code or text files, to find made-up or paraphrased quotes, or before handing over text that cites files. Not for judging whether a source supports a claim, formatting references, checking links or fetching web pages.
license: MIT
compatibility: Python 3.10+ (standard library only). No network access.
---

# Check quotes and citations against the source files

Your next step is one command, run in the user's folder. Do not list, read or search the files first, do not open
this skill's other files and do not run `--help`: the script finds the report, reads the sources and prints the fixes.
`scripts/quote_proof.py` is in this skill's folder, so call it by its full path.

The user only wants a check:

```
python3 scripts/quote_proof.py verify REPORT.md --root . --lang en
```

The user also wants the quotes or anchors fixed:

```
python3 scripts/quote_proof.py verify REPORT.md --root . --lang en --fix
```

- Leave out `REPORT.md` when the user did not name the report: the script then uses the only Markdown file under
  `--root` whose quotes cite a source. Use `--lang ko` for a Korean answer.
- `--fix` does the whole fix in the same run: it writes the copy `REPORT.fixed.md` with approximate quotes replaced by
  the exact source text and wrong `path:line` anchors corrected (the report itself is never changed), lists what is
  left to fix by hand, and re-checks the copy. The last `SUMMARY` line and the exit code are the copy's.
- A model cannot tell a word-for-word quote from a plausible paraphrase and miscounts lines; the script compares every
  quote with the real files, so trust its verdicts and answer from this one run.

## Only if `--fix` printed "left to fix by hand"

1. In `REPORT.fixed.md`, rewrite each `not_found` quote as a paraphrase without quotation marks, or remove it. Never
   guess the wording. For `source_missing`, fix the path only if the right file is obvious, otherwise ask the user.
2. Run `python3 scripts/quote_proof.py verify REPORT.fixed.md --root . --lang en` once and report that result.

## Reading the output

- One table row per quote, then `SUMMARY exact=.. normalized=.. approximate=.. not_found=.. source_missing=..
  anchor_wrong=..`. Exit code 0: every quote exact or normalized with the right anchor; 1: approximate quotes or wrong
  anchors; 2: a quote not_found or a source missing; 3: a usage or input error.
- A quote is a `"..."`, curly-quoted or corner-bracket passage of at least 4 words, or a `>` blockquote; its source is
  the `(path:12)`, `(path:12-15)`, `(path:p.3)`, `[text](path#L12-L20)` or `[^n]` footnote right after it. Without a
  source the script searches the text files under `--root` (`--source FILE` limits that). Sources outside `--root` are
  never read. Details only if needed: references/verdicts.md, references/anchors.md.

## Report back

- Paste the verdict table rows and the `SUMMARY` line as printed, then say in plain words which quotes are fine, which
  were fixed, rewritten or removed, and which are still open.
- Quote the correct anchor the script printed (for example `src/guide.md:4-6`) when an anchor is wrong.
- `approximate` is never a pass: it can be one changed word that reverses the meaning. Say which word differs.
- This checks wording and position only. It does not tell whether a source supports a claim.
- Exit code 3 (for example no report found): show the error line as is and stop. It says what is missing; ask the
  user for it instead of searching.
