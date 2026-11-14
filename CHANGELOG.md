# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.2] - 2026-11-14

### Added

- `verify --fix` checks the report, writes the corrected copy `REPORT.fixed.md`, lists what is left to fix by hand
  (`not_found`, `source_missing`) and re-checks the copy in one run; `verify --write FILE` does the same with another
  file name. The last `SUMMARY` line and the exit code are the copy's.
- `verify` and `suggest` without a report path use the only Markdown file under `--root` whose quotes cite a source;
  with none or several they exit 3 with a message that says what to pass.

### Changed

- Writing a corrected copy over an existing file prints one warning line (EN/KO); the too-large source
  warning names the 5 MB limit and what to do.
- `SKILL.md` gives one command for a check and one for check-and-fix, and tells the agent not to explore the folder or
  read help first, so the skill finishes in a few turns.
- The `task-korean-spacing` and `task-ellipsis-order` graders pin the whole verdict table row.

## [0.1.1] - 2026-11-14

### Changed

- `SKILL.md` runs `verify` as the first command and stops there for check-only requests, so the skill finishes in few turns.
- Evaluation graders now pin the exact verdict table rows (verdict, anchor label, line range, ratio) the script prints.

## [0.1.0] - 2026-11-14

### Added

- `quote_proof.py` with the subcommands `extract`, `verify` and `suggest` (standard library only, Python 3.10+).
- Quote extraction from Markdown reports: inline quotes (straight, curly, corner brackets), blockquotes as one item,
  `(path:N)`, `(path:N-M)`, `(path:p.N)` anchors, Markdown links with `#L12-L20` and footnote reference/definition pairs;
  code spans and fenced code are ignored.
- Verdicts `exact`, `normalized` (with the list of ignored steps), `approximate` (similarity ratio, changed words),
  `not_found` and `source_missing`, and anchor results `ok`, `wrong_line`, `wrong_file` and `none`.
- Nine normalization steps (`nfkc`, `quotes`, `dashes`, `whitespace`, `dehyphen`, `case`, `md_markup`, `ellipsis`,
  `cjk_spacing`) with an exact map from normalized positions back to original offsets and lines.
- Approximate alignment by word (characters for Korean, Japanese and Chinese) with n-gram candidate narrowing for large
  sources; `difflib` runs with `autojunk=False`.
- HTML sources with original line numbers and form-feed page anchors.
- `suggest --write` writes a corrected copy (approximate quotes replaced by the source text, wrong anchors rewritten);
  it refuses to overwrite the report.
- English and Korean output (`--lang`, `QUOTE_PROOF_LANG`, `LC_ALL`/`LC_MESSAGES`/`LANG`); verdict tokens, JSON keys and
  the `SUMMARY` line are identical in both languages.
- Agent skill (`SKILL.md`), Claude Code plugin manifests, evaluation set and sample files.
