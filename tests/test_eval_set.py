"""AC-8: the evaluation set - composition, text-only fixtures and pinned values that match the real script output."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

import quote_proof as qp
from conftest import REPO

EVALS = REPO / "evals"
NAME = "quote-proof"
TEXT_SUFFIXES = {".md", ".txt", ".html", ".htm"}
# forbidden machine-specific path prefixes, assembled so this file does not contain them itself
FORBIDDEN = ["/pri" + "vate/tmp", "/Us" + "ers", "/Vol" + "umes"]


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    block = text.split("---\n", 2)[1]
    out = {}
    for line in block.strip().split("\n"):
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("'") and v.endswith("'"):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def prompt_body(case: Path) -> str:
    return (case / "prompt.md").read_text(encoding="utf-8").split("---\n", 2)[2].strip()


def cases(prefix: str) -> list:
    return sorted(d for d in EVALS.iterdir() if d.is_dir() and d.name.startswith(prefix))


def test_composition_meets_the_minimums():
    trigger, notrigger = cases("trigger-"), cases("notrigger-")
    near, tasks = cases("notrigger-near-"), cases("task-")
    assert len(trigger) >= 10 and len(notrigger) >= 10 and len(near) >= 5 and len(tasks) >= 5
    assert any(d.name.startswith("task-error-") for d in tasks)
    korean = [d for d in trigger if re.search(r"[가-힣]", prompt_body(d))]
    assert len(korean) >= 2
    assert {d.name for d in EVALS.iterdir() if d.is_dir()} == {
        d.name for d in trigger + notrigger + tasks} | {"fixtures"}


def test_trigger_prompts_do_not_name_the_tool():
    for d in cases("trigger-"):
        body = prompt_body(d)
        assert not re.search(rf"\b{NAME}\b|\bskill\b|스킬|quote_proof", body, re.I), d.name
        g = frontmatter(d / "graders" / "skill-fired.md")
        assert (g["type"], g["tool"], g["arm"]) == ("tool_used", "Skill", "both") and NAME in g["input_match"]


def test_trigger_prompts_are_varied():
    bodies = [prompt_body(d) for d in cases("trigger-")]
    assert len(set(bodies)) == len(bodies)
    assert len({b.split()[0] for b in bodies}) >= 7


def test_notrigger_graders():
    for d in cases("notrigger-"):
        g = frontmatter(d / "graders" / "skill-not-fired.md")
        assert (g["type"], g["tool"], g["max"], g["arm"]) == ("tool_used", "Skill", "0", "both"), d.name


def test_prompt_frontmatter_keys_are_allowed():
    allowed = {"name", "description", "tags", "runs", "expected_outcome", "max_turns", "timeout_seconds", "allowed_tools"}
    for d in cases(""):
        if d.name == "fixtures":
            continue
        fm = frontmatter(d / "prompt.md")
        assert set(fm) <= allowed and fm["name"] == d.name


def test_task_cases_have_script_and_value_graders():
    for d in cases("task-"):
        ran = frontmatter(d / "graders" / "script-ran.md")
        assert (ran["type"], ran["tool"], ran["arm"]) == ("tool_used", "Bash", "with-only")
        assert re.search(ran["input_match"], f"python3 /x/skills/{NAME}/scripts/quote_proof.py verify report.md")
        regexes = [frontmatter(g)["pattern"] for g in sorted((d / "graders").glob("*.md"))
                   if frontmatter(g).get("type") == "regex"]
        assert len(regexes) >= 2, d.name
        for rx in regexes:
            assert len(rx) >= 6 and "\\\\" not in rx and not re.search(r"\(\?P|\\A|\\Z", rx), (d.name, rx)
        assert (d / "prompt.md").is_file() and (EVALS / "fixtures" / d.name / "report.md").is_file(), d.name


def test_fixtures_are_text_sources_and_markdown_reports_only():
    for d in sorted((EVALS / "fixtures").iterdir()):
        assert d.name.startswith("task-") and (EVALS / d.name).is_dir()
        files = [f for f in d.rglob("*") if f.is_file()]
        assert files and all(f.suffix in TEXT_SUFFIXES for f in files), d.name
        assert not [f for f in d.rglob("*") if any(part.startswith(".") for part in f.relative_to(d).parts)]
        for f in files:
            f.read_text(encoding="utf-8")        # plain UTF-8 text, no images or binaries
        assert (d / "report.md").is_file()


def test_no_machine_specific_paths_in_tests_or_evals():
    for base in (REPO / "tests", EVALS):
        for f in base.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".md", ".txt", ".html", ".htm", ".json"} and "__pycache__" not in f.parts:
                text = f.read_text(encoding="utf-8")
                for bad in FORBIDDEN:
                    assert bad not in text, f"{bad} in {f.relative_to(REPO)}"


def test_error_case_covers_a_missing_source():
    err = cases("task-error-")
    assert err
    rx = frontmatter(err[0] / "graders" / "summary-line.md")["pattern"]
    assert "source_missing=1" in rx


@pytest.mark.parametrize("case", [d.name for d in cases("task-")])
def test_pinned_values_match_the_real_script_output(case, tmp_path, monkeypatch, capsys):
    """Run the script on a copy of the fixture the way an agent would (root = the fixture folder)."""
    work = tmp_path / case
    shutil.copytree(EVALS / "fixtures" / case, work)
    monkeypatch.chdir(work)
    qp.main(["verify", "report.md", "--lang", "en"])
    out = capsys.readouterr().out
    for g in sorted((EVALS / case / "graders").glob("*.md")):
        fm = frontmatter(g)
        if fm["type"] == "regex":
            assert re.search(fm["pattern"], out), (case, g.name, out)
    # the SUMMARY pattern is an exact line, not a loose match
    summary = frontmatter(EVALS / case / "graders" / "summary-line.md")["pattern"]
    assert out.rstrip("\n").split("\n")[-1] == summary


def test_found_place_graders_pin_a_whole_verdict_row():
    """A loose pattern (just a path or a count) can be written without running the script and lets a broken
    script survive mutation testing; every task pins one table row: line, form, verdict, source/anchor, note."""
    verdicts = r"(exact|normalized|approximate|not_found|source_missing)"
    for d in cases("task-"):
        rx = frontmatter(d / "graders" / "found-place.md")["pattern"]
        assert re.match(r"\d+\\s\+(inline|block)\\s\+" + verdicts + r"\\s\+", rx), (d.name, rx)
        assert rx.count("\\s+") >= 4, (d.name, rx)


def test_trigger_cases_can_finish_in_their_turn_budget():
    """Trigger prompts run with a small turn budget in an empty folder: the SKILL.md path must be one command,
    and in an empty folder that command must stop at once with an exit-3 message instead of making the agent search."""
    for d in cases("trigger-"):
        assert int(frontmatter(d / "prompt.md")["max_turns"]) >= 4, d.name


def test_unnamed_report_in_an_empty_folder_stops_with_one_message(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert qp.main(["verify", "--root", ".", "--lang", "en", "--fix"]) == 3
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "ask the user which report to check" in err


def test_task_prompts_ask_for_the_summary_line_and_forbid_edits():
    for d in cases("task-"):
        body = prompt_body(d)
        assert "SUMMARY line" in body and "Do not edit any file" in body
