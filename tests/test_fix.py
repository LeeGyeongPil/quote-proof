"""AC-4 (one-run path): verify --fix checks, writes the corrected copy and re-checks it; verify finds the report itself.

These are the paths SKILL.md tells an agent to take, so a whole check-and-fix fits in a single command.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import quote_proof as qp
from conftest import REPO

Q = "the cache will hold stale schema entries for up to ten minutes"
BEFORE = "SUMMARY exact=0 normalized=4 approximate=1 not_found=2 source_missing=0 anchor_wrong=1"
AFTER = "SUMMARY exact=0 normalized=5 approximate=0 not_found=2 source_missing=0 anchor_wrong=0"
SKILL = REPO / "skills" / "quote-proof" / "SKILL.md"
SCRIPT = REPO / "skills" / "quote-proof" / "scripts" / "quote_proof.py"


def test_fix_prints_verdicts_fixes_todo_and_recheck_in_one_run(cli, sample):
    report = sample / "report.md"
    before_bytes = report.read_bytes()
    res = cli("verify", str(report), "--root", str(sample), "--fix")
    lines = res.out.rstrip("\n").split("\n")
    # 1) the verdicts of the report, 2) the fixes, 3) what is left by hand, 4) the re-check of the copy
    assert BEFORE in lines
    assert "  anchor: src/guide.md:9 -> src/guide.md:4-6" in lines
    assert "  > Always run the migration script before restarting the service" in lines
    assert "SUGGEST quote_fixes=1 anchor_fixes=1 unfixable=2" in lines
    assert sum(1 for ln in lines if re.match(r"  #\d \(Line \d+\) not_found: rewrite it as a paraphrase", ln)) == 2
    assert any(ln.startswith("re-check of the corrected copy") for ln in lines)
    assert lines[-1] == AFTER and res.code == 2          # exit code and last line belong to the copy
    assert lines.index(BEFORE) < lines.index("SUGGEST quote_fixes=1 anchor_fixes=1 unfixable=2") < len(lines) - 1
    # the report is untouched, the copy sits next to it
    assert report.read_bytes() == before_bytes
    assert (sample / "report.fixed.md").is_file()


def test_fix_copy_is_the_same_as_suggest_write(cli, sample, tmp_path):
    cli("verify", str(sample / "report.md"), "--root", str(sample), "--fix")
    other = tmp_path / "via-suggest.md"
    cli("suggest", str(sample / "report.md"), "--root", str(sample), "--write", str(other))
    assert (sample / "report.fixed.md").read_bytes() == other.read_bytes()
    # and verifying the copy separately gives the same final SUMMARY
    assert cli("verify", str(sample / "report.fixed.md"), "--root", str(sample)).summary == AFTER


def test_write_on_verify_implies_fix_with_that_name(cli, sample, tmp_path):
    target = tmp_path / "out" / "clean.md"
    target.parent.mkdir()
    res = cli("verify", str(sample / "report.md"), "--root", str(sample), "--write", str(target))
    assert res.code == 2 and res.summary == AFTER and target.is_file()
    assert not (sample / "report.fixed.md").exists()


def test_fix_refuses_to_overwrite_the_report(cli, sample):
    report = sample / "report.md"
    before = report.read_bytes()
    res = cli("verify", str(report), "--root", str(sample), "--write", str(report))
    assert res.code == 3 and "refusing to overwrite the report" in res.err
    assert report.read_bytes() == before


def test_fix_json_has_the_copy_fixes_and_after(cli, sample):
    data = cli("verify", str(sample / "report.md"), "--root", str(sample), "--fix", "--json").json()
    assert data["summary"]["approximate"] == 1 and data["summary"]["anchor_wrong"] == 1
    assert data["fixes"] == {"quote": 1, "anchor": 1}
    assert data["copy"].endswith("report.fixed.md")
    assert data["after"]["summary"] == {"exact": 0, "normalized": 5, "approximate": 0, "not_found": 2,
                                        "source_missing": 0, "anchor_wrong": 0}


def test_fix_with_out_writes_everything_to_the_file(cli, sample, tmp_path):
    out = tmp_path / "result.txt"
    res = cli("verify", str(sample / "report.md"), "--root", str(sample), "--fix", "--out", str(out))
    assert res.out.rstrip("\n").split("\n")[-1] == AFTER and res.code == 2
    text = out.read_text(encoding="utf-8")
    assert BEFORE in text and "SUGGEST quote_fixes=1" in text and "re-check of the corrected copy" in text


def test_fix_on_a_clean_report_exits_0_without_todo(cli, tree, tmp_path):
    root = tree({"g.md": f"{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Cited "{Q}" (g.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root), "--fix")
    assert res.code == 0 and "Nothing to fix automatically." in res.out
    assert "left to fix by hand" not in res.out


def test_fix_lists_a_missing_source_with_its_path(cli, tree, tmp_path):
    root = tree({"g.md": "nothing\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Cited "{Q}" (gone.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root), "--fix")
    assert res.code == 2
    assert "  #1 (Line 1) source_missing: cannot read gone.md; fix the path or ask for the file" in res.out


def test_fix_warnings_are_printed_once(cli, tree, tmp_path):
    root = tree({"bad.md": b"\xff\xfe broken"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Said "{Q}" (bad.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root), "--fix")
    assert res.err.count("cannot read source: bad.md") == 1


# ---------- the report is found without a path ----------

def test_report_is_found_when_it_is_the_only_one(cli, sample, monkeypatch):
    explicit = cli("verify", str(sample / "report.md"), "--root", str(sample))
    monkeypatch.chdir(sample)
    found = cli("verify")
    assert found.out == explicit.out and found.code == explicit.code == 2      # same stdout: table and SUMMARY
    assert found.err == "checking report.md (the only Markdown file here whose quotes cite a source)\n"


def test_report_search_skips_fixed_copies_sources_and_hidden_folders(cli, sample, monkeypatch):
    (sample / ".cache").mkdir()
    (sample / ".cache" / "old.md").write_text(f'Old "{Q}" (src/guide.md:1).\n', encoding="utf-8")
    monkeypatch.chdir(sample)
    assert cli("verify", "--fix").code == 2            # writes report.fixed.md
    again = cli("verify")                              # the copy does not compete with the report
    assert again.code == 2 and again.summary == BEFORE
    assert "checking report.md" in again.err


def test_report_search_ignores_markdown_without_anchored_quotes(cli, tree, tmp_path, monkeypatch):
    root = tree({"notes.md": f'He said "{Q}" once.\n', "g.md": f"{Q}.\n"})
    monkeypatch.chdir(root)
    res = cli("verify")
    assert res.code == 3 and "no report given" in res.err


def test_suggest_also_finds_the_report(cli, sample, monkeypatch):
    monkeypatch.chdir(sample)
    res = cli("suggest")
    assert res.code == 0 and res.summary == "SUGGEST quote_fixes=1 anchor_fixes=1 unfixable=2"


def test_report_search_finds_nested_reports(cli, sample, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = cli("verify", "--root", "sample")
    assert res.code == 2 and "checking sample/report.md" in res.err


# ---------- SKILL.md commands are the one-run commands and really work ----------

def _skill_commands() -> list:
    text = SKILL.read_text(encoding="utf-8")
    return [b.strip() for b in re.findall(r"```\n(.*?)```", text, re.S)]


def test_skill_md_starts_with_the_one_run_commands():
    cmds = _skill_commands()
    assert cmds[0] == "python3 scripts/quote_proof.py verify REPORT.md --root . --lang en"
    assert cmds[1] == "python3 scripts/quote_proof.py verify REPORT.md --root . --lang en --fix"
    body = SKILL.read_text(encoding="utf-8").split("---", 2)[2]
    assert "Do not list, read or search the files first" in body and "do not run `--help`" in body
    # the old multi-step loop (suggest, then verify again) is gone from the instructions
    assert "suggest REPORT.md" not in body


def test_skill_md_frontmatter_has_no_inline_comment_and_keeps_use_when():
    front = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
    assert " #" not in front and "Use when" in front


def test_skill_md_commands_run_as_written(sample):
    """Run the documented commands the way an agent would: in the user's folder, script by full path."""
    for cmd in _skill_commands():
        argv = cmd.split()
        assert argv[:2] == ["python3", "scripts/quote_proof.py"]
        argv = [sys.executable, str(SCRIPT)] + ["report.md" if a == "REPORT.md" else a for a in argv[2:]]
        proc = subprocess.run(argv, cwd=sample, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 2, proc.stderr
        assert proc.stdout.rstrip("\n").split("\n")[-1] in (BEFORE, AFTER)
    # the report path may be left out too (the SKILL.md rule for an unnamed report)
    proc = subprocess.run([sys.executable, str(SCRIPT), "verify", "--root", ".", "--lang", "en", "--fix"],
                          cwd=sample, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and proc.stdout.rstrip("\n").split("\n")[-1] == AFTER


def test_fixed_name_keeps_the_folder_and_suffix():
    assert qp._fixed_name(Path("a/b/report.md")) == Path("a/b/report.fixed.md")
    assert qp._fixed_name(Path("notes.markdown")) == Path("notes.fixed.markdown")


def test_sample_fixture_ignores_generated_copies(cli):
    """A README run leaves sample/report.fixed.md behind; tests must still pass with it present."""
    stray = REPO / "sample" / "report.fixed.md"
    existed = stray.exists()
    stray.write_text("stale\n", encoding="utf-8")
    try:
        res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", str(Path(__file__).parent / "test_fix.py"),
                              "-k", "not sample_fixture_ignores"], capture_output=True, text=True, cwd=REPO)
        assert res.returncode == 0, res.stdout + res.stderr
    finally:
        if not existed:
            stray.unlink()


def test_fix_warns_when_it_overwrites_an_existing_copy(cli, sample):
    report = sample / "report.md"
    first = cli("verify", str(report), "--root", str(sample), "--fix")
    assert "overwriting" not in first.err
    second = cli("verify", str(report), "--root", str(sample), "--fix")
    assert "overwriting the existing copy" in second.err and "report.fixed.md" in second.err
    ko = cli("verify", str(report), "--root", str(sample), "--fix", "--lang", "ko")
    assert "기존 사본을 덮어씁니다" in ko.err


def test_symbol_word_fix_copy_holds_exactly_the_quoted_range_in_both_languages(cli, tree, tmp_path):
    root = tree({"src.md": "Backups run daily & logs rotate weekly on the main server.\n",
                 "r.md": '# R\n\nIt says "Backups run daily and logs rotate weekly" (src.md:1)\n'}, folder=".")
    out = tmp_path / "r.fixed.md"
    for lang, note in (("en", "1 word(s) changed"), ("ko", "단어 1개 다름")):
        res = cli("verify", str(root / "r.md"), "--root", str(root), "--write", str(out), "--lang", lang)
        assert note in res.out
        copy = out.read_text(encoding="utf-8")
        assert '"Backups run daily & logs rotate weekly" (src.md:1)' in copy
        assert "weekly on" not in copy
        out.unlink()
    html = tree({"s.html": "<p>The quick brown fox &amp; the lazy dog jumped over the fence.</p>\n",
                 "r.md": '# R\n\n"The quick brown fox and the lazy dog jumped" (s.html:1)\n'}, folder=".")
    data = cli("suggest", str(html / "r.md"), "--root", str(html), "--json").json()
    assert data["items"][0]["suggestion"]["replace_quote"] == "The quick brown fox & the lazy dog jumped"
