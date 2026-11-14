# Quotes and citation syntax

## What counts as a quote

- Inline: `"..."`, `“...”`, `「...」`, `『...』` in a paragraph. A quote may wrap over lines of the paragraph.
- A `>` blockquote is one quote (consecutive `>` lines). Short quotes inside it are not extracted separately.
- Single quotes are never quotes. Code spans and fenced code blocks (``` or ~~~) are ignored.
- Quotes shorter than `--min-words` (default 4 words; for Korean, Japanese and Chinese text twice as many characters)
  are treated as emphasis and skipped.

## Where the source is named

| Syntax | Example |
|---|---|
| line | `"..." (src/guide.md:12)` |
| line range | `"..." (src/guide.md:12-15)` |
| page of form-feed separated text | `"..." (paper.txt:p.3)` |
| file only | `"..." (src/guide.md)` |
| Markdown link with lines | `"..." [guide](src/guide.md#L12-L20)` |
| footnote | `"..."[^1]` with `[^1]: src/guide.md:12-15` or `[^1]: [guide](src/guide.md#L12)` |

- The anchor must follow the quote before the next quote of the same paragraph. For a blockquote it is the end of the
  last line.
- Paths are relative to `--root`. Every path (anchors, `--source`, options) goes through one rule: surrounding spaces
  dropped, backslashes turned into slashes, `./` and `//` removed, `a/../b` collapsed. A path that leaves `--root`
  (also through a symbolic link) is not read.
- `http://` and `https://` links are not sources. Fetch the page yourself if the user needs it checked.

## Source files

- Any UTF-8 text (a BOM is fine): `.md`, `.txt`, `.rst`, code, config. Without an anchor the script searches common
  text and code extensions under `--root`, skipping `.git`, `node_modules`, hidden folders and the report itself
  (and files that repeat at least half of the report's lines, such as a corrected copy).
- `.html` and `.htm` are turned into text; reported lines are lines of the HTML file.
- Text split into pages by form feeds (for example from `pdftotext`) supports `p.N`. PDFs and other binaries are not read.
- Files over 5 MB are skipped with a warning.
