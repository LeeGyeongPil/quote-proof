"""AC-4: suggestions, the corrected copy and the refusal to overwrite the report."""
from __future__ import annotations

Q = "the cache will hold stale schema entries for up to ten minutes"


def test_suggest_shows_source_span_and_corrected_anchor(cli, sample):
    res = cli("suggest", str(sample / "report.md"), "--root", str(sample))
    assert res.code == 0
    assert "src/guide.md:9 -> src/guide.md:4-6" in res.out
    assert "> Always run the migration script before restarting the service" in res.out
    assert res.summary == "SUGGEST quote_fixes=1 anchor_fixes=1 unfixable=2"


def test_suggest_json_carries_the_fixes(cli, sample):
    data = cli("suggest", str(sample / "report.md"), "--root", str(sample), "--json").json()
    by_line = {i["report_line"]: i for i in data["items"]}
    assert by_line[5]["suggestion"] == {"replace_quote": None, "anchor": "src/guide.md:4-6"}
    assert by_line[17]["suggestion"] == {
        "replace_quote": "Always run the migration script before restarting the service", "anchor": None}
    assert by_line[7]["suggestion"] is None and by_line[13]["suggestion"] is None
    assert data["fixes"] == {"quote": 1, "anchor": 1} and data["copy"] is None


def test_write_copy_reverifies_with_only_not_found_left(cli, sample, tmp_path):
    fixed = tmp_path / "fixed.md"
    res = cli("suggest", str(sample / "report.md"), "--root", str(sample), "--write", str(fixed))
    assert res.code == 0 and "wrote the corrected copy" in res.out
    again = cli("verify", str(fixed), "--root", str(sample))
    assert again.code == 2
    assert again.summary == "SUMMARY exact=0 normalized=5 approximate=0 not_found=2 source_missing=0 anchor_wrong=0"


def test_write_copy_changes_only_the_fixed_places(cli, sample, tmp_path):
    fixed = tmp_path / "fixed.md"
    cli("suggest", str(sample / "report.md"), "--root", str(sample), "--write", str(fixed))
    before = (sample / "report.md").read_text(encoding="utf-8").split("\n")
    after = fixed.read_text(encoding="utf-8").split("\n")
    changed = [i + 1 for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and changed == [5, 17]
    assert "(src/guide.md:4-6)" in after[4]
    assert "before restarting the service" in after[16]
    # the original report is untouched
    assert "(src/guide.md:9)" in before[4]


def test_not_found_quotes_are_left_alone(cli, sample, tmp_path):
    fixed = tmp_path / "fixed.md"
    cli("suggest", str(sample / "report.md"), "--root", str(sample), "--write", str(fixed))
    text = fixed.read_text(encoding="utf-8")
    assert "safe mode disables the HTTP API" in text and "never restart without a backup" in text


def test_wrong_file_anchor_is_rewritten_to_the_right_file(cli, tree, tmp_path):
    root = tree({"guide.md": "nothing about it\n", "ops.md": f"# Ops\n\n{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'The note says "{Q}" (guide.md:2).\n')
    fixed = tmp_path / "fixed.md"
    assert cli("suggest", str(rep), "--root", str(root), "--write", str(fixed)).code == 0
    assert fixed.read_text(encoding="utf-8") == f'The note says "{Q}" (ops.md:3).\n'
    assert cli("verify", str(fixed), "--root", str(root)).code == 0


def test_link_and_footnote_anchor_styles_are_kept(cli, tree, tmp_path):
    root = tree({"g.md": f"first\nsecond\n{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Link: "{Q}" ([g](g.md#L1-L2)).\n\nNote: "{Q}"[^1].\n\n[^1]: g.md:1\n')
    fixed = tmp_path / "fixed.md"
    cli("suggest", str(rep), "--root", str(root), "--write", str(fixed))
    text = fixed.read_text(encoding="utf-8")
    assert "([g](g.md#L3))" in text and "[^1]: g.md:3" in text
    assert cli("verify", str(fixed), "--root", str(root)).code == 0


def test_page_anchor_is_rewritten(cli, tree, tmp_path):
    root = tree({"p.txt": f"one\n\f{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Cited "{Q}" (p.txt:p.1).\n')
    fixed = tmp_path / "fixed.md"
    cli("suggest", str(rep), "--root", str(root), "--write", str(fixed))
    assert "(p.txt:p.2)" in fixed.read_text(encoding="utf-8")


def test_block_quote_is_replaced_by_the_source_span(cli, tree, tmp_path):
    root = tree({"g.md": "Always run the migration script before restarting the\nservice; then check the logs.\n"})
    rep = tmp_path / "r.md"
    rep.write_text("> Always run the migration script after restarting the service. (g.md:1)\n")
    fixed = tmp_path / "fixed.md"
    cli("suggest", str(rep), "--root", str(root), "--write", str(fixed))
    assert fixed.read_text(encoding="utf-8") == (
        "> Always run the migration script before restarting the service (g.md:1)\n")
    assert cli("verify", str(fixed), "--root", str(root)).code == 0


def test_nothing_to_fix(cli, tree, tmp_path):
    root = tree({"g.md": f"{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Cited "{Q}" (g.md:1).\n')
    res = cli("suggest", str(rep), "--root", str(root))
    assert res.code == 0 and "Nothing to fix automatically." in res.out
    assert res.summary == "SUGGEST quote_fixes=0 anchor_fixes=0 unfixable=0"


def test_write_to_the_report_path_is_refused_with_exit_3(cli, sample):
    report = sample / "report.md"
    before = report.read_bytes()
    res = cli("suggest", str(report), "--root", str(sample), "--write", str(report))
    assert res.code == 3 and "refusing to overwrite the report" in res.err
    assert report.read_bytes() == before


def test_write_refusal_uses_the_same_path_rule(cli, sample):
    report = sample / "report.md"
    for spelling in (str(sample / "." / "report.md"), str(sample / "src" / ".." / "report.md"),
                     str(sample) + "//report.md"):
        res = cli("suggest", str(report), "--root", str(sample), "--write", spelling)
        assert res.code == 3, spelling
