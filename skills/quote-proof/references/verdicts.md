# Verdicts, normalization steps and exit codes

## Verdicts

| Verdict | Meaning | Fix |
|---|---|---|
| `exact` | The quote is a character-for-character substring of the source. | none |
| `normalized` | Same words and letters after folding print differences; the ignored steps are listed. | none |
| `approximate` | The closest passage is at least `--min-ratio` (default 0.8) similar, but words differ. The note shows the ratio and the number of changed words (or characters for CJK). | `suggest` gives the exact source text |
| `not_found` | Nothing in the sources is close enough. The note shows the closest ratio. | paraphrase without quotation marks, or remove |
| `source_missing` | The cited file does not exist, cannot be read as UTF-8 text, is over 5 MB or is outside `--root`; or nothing was searchable. | fix the path |

## Anchor column

| Anchor | Meaning |
|---|---|
| `ok` | The found lines overlap the claimed lines (or the claimed page / file matches). |
| `wrong_line` | Found in the cited file, but not at the claimed lines or page. |
| `wrong_file` | Not in the cited file, but word for word in another file under the root. |
| `none` | The quote has no source, or it was not found. |

`suggest` rewrites `wrong_line` and `wrong_file` anchors in the same syntax (`(path:4-6)`, `path#L4-L6`, footnote
`path:4-6`, `path:p.2`).

## Normalization steps (only steps used inside the matched passage are listed)

| Step | Folds |
|---|---|
| `nfkc` | compatibility forms: ligatures, full-width letters |
| `quotes` | curly and low quotation marks to straight ones |
| `dashes` | en dash, em dash, minus sign to a hyphen |
| `whitespace` | runs of spaces, tabs, line breaks, non-breaking spaces to one space |
| `dehyphen` | a word split with a hyphen at a line end (both joined and kept hyphen are tried) and soft hyphens |
| `case` | upper and lower case |
| `md_markup` | `**`, `*`, backticks, `~~`, `__`, and `>` markers of a quoted source |
| `ellipsis` | `[...]`, `...` or the ellipsis character between fragments, which must appear in that order |
| `cjk_spacing` | spaces next to Korean, Japanese or Chinese characters |

Words are never changed: a different word, ending or synonym is not folded away, so `before` versus `after` is never
`normalized`.

## Exit codes

| Code | When |
|---|---|
| 0 | every quote is `exact` or `normalized` and no anchor is wrong (also when the report has no quotes) |
| 1 | at least one `approximate` quote or wrong anchor, and no `not_found` or `source_missing` |
| 2 | at least one `not_found` or `source_missing` |
| 3 | usage or input error (missing report, no or several reports found, bad option, report not UTF-8, refused overwrite) |

`verify --fix` returns the exit code of the corrected copy `REPORT.fixed.md` after it has re-checked it, so one run
gives the remaining state. `suggest` exits 0 when it ran, so `suggest ... --write FIXED.md && verify FIXED.md` also
works.
