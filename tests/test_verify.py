"""AC-3: verdicts on the sample, wrong_file, source_missing, HTML and page sources, exit codes."""
from __future__ import annotations

import subprocess
import sys

from conftest import REPO

SCRIPT = REPO / "skills" / "quote-proof" / "scripts" / "quote_proof.py"
Q = "the cache will hold stale schema entries for up to ten minutes"


def items_of(res):
    return {i["report_line"]: i for i in res.json()["items"]}


# ---------- the sample (probe table) ----------

def test_sample_summary_and_exit_code(cli, sample):
    res = cli("verify", str(sample / "report.md"), "--root", str(sample))
    assert res.summary == "SUMMARY exact=0 normalized=4 approximate=1 not_found=2 source_missing=0 anchor_wrong=1"
    assert res.code == 2


def test_sample_verdict_table(cli, sample):
    got = items_of(cli("verify", str(sample / "report.md"), "--root", str(sample), "--json"))
    assert {k: v["verdict"] for k, v in got.items()} == {
        3: "normalized", 5: "normalized", 7: "not_found", 9: "normalized", 11: "normalized", 13: "not_found",
        17: "approximate"}
    # the hyphenated quote sits at src/guide.md:4-6 while the report claims line 9
    hy = got[5]
    assert hy["anchor"] == "wrong_line"
    assert (hy["found"]["path"], hy["found"]["line_start"], hy["found"]["line_end"]) == ("src/guide.md", 4, 6)
    assert hy["claimed"]["line_start"] == 9 and hy["steps"] == ["whitespace", "dehyphen"]
    # one word changed: before -> after
    ap = got[17]
    assert (ap["ratio"], ap["changed_units"], ap["unit"]) == (0.889, 1, "word")
    assert "before restarting the" in ap["found"]["text"]
    assert ap["suggestion"]["replace_quote"] == "Always run the migration script before restarting the service"
    # block quote with ellipsis and curly quotes, no anchor
    assert got[9]["steps"] == ["quotes", "whitespace", "ellipsis"] and got[9]["anchor"] == "none"
    # Korean spacing
    assert got[11]["steps"] == ["cjk_spacing"] and got[11]["found"]["path"] == "src/notes_ko.txt"
    # report_line and source line keys stay separate
    assert got[5]["report_line"] == 5 and got[5]["found"]["line_start"] == 4


def test_json_has_fixed_keys(cli, sample):
    data = cli("verify", str(sample / "report.md"), "--root", str(sample), "--json").json()
    assert set(data) == {"tool", "version", "report", "root", "summary", "items", "warnings"}
    assert set(data["summary"]) == {"exact", "normalized", "approximate", "not_found", "source_missing", "anchor_wrong"}
    assert set(data["items"][0]) == {"id", "report_line", "kind", "quote", "claimed", "verdict", "steps", "ratio",
                                     "changed_units", "unit", "found", "anchor", "also_in", "suggestion"}


def test_sample_runs_as_a_script():
    p = subprocess.run([sys.executable, "-I", str(SCRIPT), "verify", "sample/report.md", "--root", "sample"],
                       cwd=REPO, capture_output=True, text=True, env={"LANG": "C"})
    assert p.returncode == 2
    assert p.stdout.rstrip().endswith(
        "SUMMARY exact=0 normalized=4 approximate=1 not_found=2 source_missing=0 anchor_wrong=1")


# ---------- wrong_file, source_missing, anchors ----------

def test_misattributed_quote_is_wrong_file(cli, tree, tmp_path):
    root = tree({"guide.md": "# Guide\nOnly the guide talks about backups here, nothing else.\n",
                 "ops.md": f"# Ops\n\n{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'The ops note says "{Q}" (guide.md:2).\n')
    it = items_of(cli("verify", str(rep), "--root", str(root), "--json"))[1]
    assert it["verdict"] == "exact" and it["anchor"] == "wrong_file"
    assert it["found"]["path"] == "ops.md" and it["found"]["line_start"] == 3
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 1 and "wrong_file" in res.out and res.summary.endswith("anchor_wrong=1")


def test_missing_source_file(cli, tree, tmp_path):
    root = tree({"guide.md": "x\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'The notes say "{Q}" (gone.md:2).\n')
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 2 and "source_missing" in res.out
    assert res.summary == "SUMMARY exact=0 normalized=0 approximate=0 not_found=0 source_missing=1 anchor_wrong=0"
    assert items_of(cli("verify", str(rep), "--root", str(root), "--json"))[1]["verdict"] == "source_missing"


def test_unreadable_source_is_source_missing_with_warning(cli, tree, tmp_path):
    root = tree({"bin.md": b"\xff\xfe\x00bad bytes"})
    rep = tmp_path / "r.md"
    rep.write_text(f'The notes say "{Q}" (bin.md:2).\n')
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 2 and "warning: cannot read source: bin.md" in res.err


def test_anchor_outside_root_is_refused_not_read(cli, tree, tmp_path):
    root = tree({"guide.md": "x\n"})
    (tmp_path / "secret.md").write_text(f"{Q}.\n")
    rep = tmp_path / "r.md"
    rep.write_text(f'The notes say "{Q}" (../secret.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 2 and "source is outside --root and was ignored: ../secret.md" in res.err
    assert "source_missing=1" in res.summary


def test_second_occurrence_matches_the_anchor(cli, tree, tmp_path):
    text = f"intro\n{Q}.\nmiddle\nmore\n{Q}.\n"
    root = tree({"a.md": text})
    rep = tmp_path / "r.md"
    rep.write_text(f'Quoted "{Q}" (a.md:5).\n')
    it = items_of(cli("verify", str(rep), "--root", str(root), "--json"))[1]
    assert it["anchor"] == "ok" and it["found"]["line_start"] == 5 and it["verdict"] == "exact"


def test_exact_quote_with_line_range_overlap(cli, tree, tmp_path):
    root = tree({"a.md": f"one\n{Q}\nthree\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Quoted "{Q}" (a.md:1-3).\n')
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 0 and res.summary.startswith("SUMMARY exact=1 normalized=0")


def test_anchor_path_forms_resolve_to_the_same_file(cli, tree, tmp_path):
    root = tree({"src/a.md": f"{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'One "{Q}" (./src/a.md:1).\n\nTwo "{Q}" (src\\a.md:1).\n\nThree "{Q}" (src//a.md:1).\n')
    got = cli("verify", str(rep), "--root", str(root), "--json").json()
    assert [(i["verdict"], i["anchor"]) for i in got["items"]] == [("exact", "ok")] * 3
    assert {i["claimed"]["path"] for i in got["items"]} == {"src/a.md"}


def test_no_anchor_searches_text_files_and_lists_other_matches(cli, tree, tmp_path):
    root = tree({"a.md": f"{Q}.\n", "b/c.txt": f"also: {Q}.\n", "image.png": b"\x89PNG\x00\x01"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Quoted "{Q}" without a source.\n')
    it = items_of(cli("verify", str(rep), "--root", str(root), "--json"))[1]
    assert it["found"]["path"] == "a.md" and it["also_in"] == ["b/c.txt"] and it["anchor"] == "none"


def test_source_option_limits_the_search(cli, tree, tmp_path):
    root = tree({"a.md": "nothing here\n", "b.md": f"{Q}.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Quoted "{Q}" without a source.\n')
    assert cli("verify", str(rep), "--root", str(root), "--source", "a.md").code == 2
    assert cli("verify", str(rep), "--root", str(root), "--source", "b.md").code == 0


def test_report_inside_root_is_not_its_own_source(cli, tree):
    root = tree({"a.md": "nothing relevant\n"})
    rep = root / "r.md"
    rep.write_text(f'Quoted "{Q}" without a source.\n')
    assert cli("verify", str(rep), "--root", str(root)).code == 2


# ---------- HTML and pages ----------

def test_html_source_reports_original_lines(cli, tree, tmp_path):
    html = ("<html><head><title>Doc</title><style>p { color: red }</style></head>\n<body>\n<h1>Title</h1>\n"
            f"<p>Intro text.</p>\n<p>{Q.split(' entries')[0]}\n   entries for up to <b>ten</b> minutes</p>\n"
            "<script>var x = 1;</script>\n</body></html>\n")
    root = tree({"page.html": html})
    rep = tmp_path / "r.md"
    rep.write_text(f'The page says "{Q}" (page.html:5).\n')
    it = items_of(cli("verify", str(rep), "--root", str(root), "--json"))[1]
    assert it["verdict"] in ("exact", "normalized")
    assert it["found"]["path"] == "page.html" and it["anchor"] == "ok"
    assert (it["found"]["line_start"], it["found"]["line_end"]) == (5, 6)
    assert "var x" not in it["found"]["text"]


def test_html_entities_are_decoded(cli, tree, tmp_path):
    root = tree({"p.html": "<p>Fish &amp; chips &mdash; served daily at the harbour</p>\n"})
    rep = tmp_path / "r.md"
    rep.write_text('Menu: "Fish & chips - served daily at the harbour" (p.html:1).\n')
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 0 and "normalized=1" in res.summary


def test_form_feed_text_supports_page_anchors(cli, tree, tmp_path):
    pages = f"Page one text goes here.\n\f{Q}.\nmore page two\n\fPage three.\n"
    root = tree({"paper.txt": pages})
    rep = tmp_path / "r.md"
    rep.write_text(f'Paper: "{Q}" (paper.txt:p.2).\n\nWrong page: "{Q} (same)" (paper.txt:p.3).\n\n'
                   f'Also wrong: "{Q}" (paper.txt:p.3).\n')
    got = cli("verify", str(rep), "--root", str(root), "--json").json()["items"]
    assert got[0]["anchor"] == "ok" and got[0]["found"]["page_start"] == 2
    assert got[2]["anchor"] == "wrong_line" and got[2]["suggestion"]["anchor"] == "paper.txt:p.2"


# ---------- exit codes ----------

def test_exit_code_0_for_exact_and_normalized(cli, tree, tmp_path):
    root = tree({"a.md": f"{Q}.\n\nSecond line of the \u201cdoc\u201d is long enough.\n"})
    rep = tmp_path / "r.md"
    rep.write_text(f'A "{Q}" (a.md:1).\n\nB "second line of the \u201cdoc\u201d is long enough" (a.md:3).\n')
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 0, res.out
    assert res.summary.startswith("SUMMARY exact=1 normalized=1 approximate=0")


def test_exit_code_1_for_approximate_only(cli, tree, tmp_path):
    root = tree({"a.md": "Always run the migration script before restarting the service.\n"})
    rep = tmp_path / "r.md"
    rep.write_text('Said "Always run the migration script after restarting the service" (a.md:1).\n')
    assert cli("verify", str(rep), "--root", str(root)).code == 1


def test_exit_code_2_wins_over_1(cli, tree, tmp_path):
    root = tree({"a.md": "Always run the migration script before restarting the service.\n"})
    rep = tmp_path / "r.md"
    rep.write_text('Said "Always run the migration script after restarting the service" (a.md:1).\n\n'
                   'And "a sentence that no source file contains at all" (a.md:1).\n')
    assert cli("verify", str(rep), "--root", str(root)).code == 2


def test_report_without_quotes_exits_0(cli, tree, tmp_path):
    root = tree({"a.md": "x\n"})
    rep = tmp_path / "r.md"
    rep.write_text("# Nothing quoted here\n")
    res = cli("verify", str(rep), "--root", str(root))
    assert res.code == 0 and "No quotes found" in res.out
    assert res.summary == "SUMMARY exact=0 normalized=0 approximate=0 not_found=0 source_missing=0 anchor_wrong=0"


def test_min_ratio_changes_approximate_to_not_found(cli, tree, tmp_path):
    root = tree({"a.md": "Always run the migration script before restarting the service.\n"})
    rep = tmp_path / "r.md"
    rep.write_text('Said "Always run the migration script after restarting the service" (a.md:1).\n')
    assert cli("verify", str(rep), "--root", str(root), "--min-ratio", "0.95").code == 2
    assert cli("verify", str(rep), "--root", str(root), "--min-ratio", "0.5").code == 1


def test_out_file_gets_the_table_and_stdout_the_summary(cli, sample, tmp_path):
    out = tmp_path / "result.txt"
    res = cli("verify", str(sample / "report.md"), "--root", str(sample), "--out", str(out))
    assert res.code == 2 and res.summary.startswith("SUMMARY exact=0 normalized=4")
    assert "wrong_line" in out.read_text(encoding="utf-8")


def test_extract_command_lists_quotes_and_claims(cli, sample):
    res = cli("extract", str(sample / "report.md"))
    assert res.code == 0 and "src/guide.md:9" in res.out and "src/notes_ko.txt:2" in res.out
    data = cli("extract", str(sample / "report.md"), "--json").json()
    assert len(data["items"]) == 7 and data["items"][3]["kind"] == "block"
