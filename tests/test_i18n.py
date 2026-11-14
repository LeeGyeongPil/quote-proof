"""AC-6: English and Korean output, language precedence and every user-facing error path in both languages."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import _qp_i18n as i18n
import _qp_sources as sources
import quote_proof as qp

LANGS = ["en", "ko"]
HANGUL = re.compile(r"[가-힣]")
Q = "the cache will hold stale schema entries for up to ten minutes"


def prefix(lang: str) -> str:
    return "error:" if lang == "en" else "오류:"


def warn_prefix(lang: str) -> str:
    return "warning:" if lang == "en" else "경고:"


# ---------- dictionaries ----------

def test_both_dictionaries_have_identical_keys():
    assert set(i18n.MESSAGES["en"]) == set(i18n.MESSAGES["ko"])


def test_placeholders_match_between_languages():
    field = re.compile(r"\{(\w+)\}")
    for key, en in i18n.MESSAGES["en"].items():
        assert set(field.findall(en)) == set(field.findall(i18n.MESSAGES["ko"][key])), key


def test_korean_messages_are_really_korean():
    for key, ko in i18n.MESSAGES["ko"].items():
        if key == "col_id":      # "#" is the same in both languages
            continue
        assert HANGUL.search(ko), key


# ---------- language rule ----------

def test_precedence_cli_over_env_over_locale(monkeypatch, cli, sample):
    report, root = str(sample / "report.md"), str(sample)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert "판정" in cli("verify", report, "--root", root).out                    # LANG
    monkeypatch.setenv("LC_MESSAGES", "en_US.UTF-8")
    assert "Verdict" in cli("verify", report, "--root", root).out                 # LC_MESSAGES beats LANG
    monkeypatch.setenv("LC_ALL", "ko_KR.UTF-8")
    assert "판정" in cli("verify", report, "--root", root).out                    # LC_ALL beats LC_MESSAGES
    monkeypatch.setenv("QUOTE_PROOF_LANG", "en")
    assert "Verdict" in cli("verify", report, "--root", root).out                 # tool variable beats LC_ALL
    assert "판정" in cli("verify", report, "--root", root, "--lang", "ko").out    # --lang beats everything
    monkeypatch.setenv("QUOTE_PROOF_LANG", "ko")
    assert "Verdict" in cli("verify", report, "--root", root, "--lang", "en").out
    assert "Verdict" in cli("verify", report, "--root", root, "--lang=en").out


def test_non_korean_locales_fall_back_to_english(monkeypatch):
    for value in ("C", "POSIX", "en_US.UTF-8", "fr_FR.UTF-8", "ja_JP.UTF-8", ""):
        assert i18n.lang_from_env({"LANG": value}) == "en", value
    assert i18n.lang_from_env({}) == "en"
    assert i18n.lang_from_env({"LANG": "ko_KR.UTF-8"}) == "ko"
    assert i18n.lang_from_env({"LC_ALL": "KO"}) == "ko"
    # an unknown value of the tool variable is ignored and the locale decides
    assert i18n.lang_from_env({"QUOTE_PROOF_LANG": "fr", "LANG": "ko_KR"}) == "ko"


def test_lang_value_is_case_insensitive(cli, sample):
    assert "판정" in cli("verify", str(sample / "report.md"), "--root", str(sample), "--lang", "KO").out


# ---------- tokens stay the same ----------

def test_verdict_tokens_json_keys_and_summary_do_not_change(cli, sample):
    args = ("--root", str(sample))
    en = cli("verify", str(sample / "report.md"), *args, "--lang", "en", "--json").json()
    ko = cli("verify", str(sample / "report.md"), *args, "--lang", "ko", "--json").json()
    assert en == ko
    t_en = cli("verify", str(sample / "report.md"), *args, "--lang", "en")
    t_ko = cli("verify", str(sample / "report.md"), *args, "--lang", "ko")
    assert t_en.summary == t_ko.summary and t_en.summary.startswith("SUMMARY exact=0 normalized=4")
    for token in ("normalized", "approximate", "not_found", "wrong_line", "inline", "block", "none", "ok"):
        assert token in t_en.out and token in t_ko.out


def test_table_headers_notes_and_notices_are_translated(cli, sample, tree, tmp_path):
    en = cli("verify", str(sample / "report.md"), "--root", str(sample), "--lang", "en").out
    ko = cli("verify", str(sample / "report.md"), "--root", str(sample), "--lang", "ko").out
    assert en.startswith("#  Line  Form") and "ignored: whitespace, dehyphen" in en and "word(s) changed" in en
    assert ko.startswith("#  줄") and "봐준 차이: whitespace, dehyphen" in ko and "단어 1개 다름" in ko
    rep = tmp_path / "none.md"
    rep.write_text("# nothing\n")
    assert "No quotes found" in cli("verify", str(rep), "--root", str(sample), "--lang", "en").out
    assert "인용을 찾지 못했습니다" in cli("verify", str(rep), "--root", str(sample), "--lang", "ko").out
    s_en = cli("suggest", str(sample / "report.md"), "--root", str(sample), "--lang", "en").out
    s_ko = cli("suggest", str(sample / "report.md"), "--root", str(sample), "--lang", "ko").out
    assert "anchor: src/guide.md:9 -> src/guide.md:4-6" in s_en and "앵커: src/guide.md:9 -> src/guide.md:4-6" in s_ko


@pytest.mark.parametrize("lang", LANGS)
def test_extract_table_uses_the_language(cli, sample, lang):
    out = cli("extract", str(sample / "report.md"), "--lang", lang).out
    assert ("Claimed source" in out) if lang == "en" else ("주장한 출처" in out)


@pytest.mark.parametrize("lang", LANGS)
def test_help_is_in_the_language(cli, capsys, lang):
    res = cli("--lang", lang, "--help")
    assert res.code == 0
    assert ("usage: " in res.out and "commands" in res.out and "Exit codes" in res.out) if lang == "en" else \
        ("사용법: " in res.out and "명령" in res.out and "종료 코드" in res.out and "usage:" not in res.out)
    sub = cli("verify", "--help", "--lang", lang)
    assert sub.code == 0
    assert ("--min-ratio" in sub.out) and (("lowest similarity" in sub.out) if lang == "en" else ("최소 유사도" in sub.out))
    assert (HANGUL.search(sub.out) is None) == (lang == "en")
    assert sub.out.startswith(("usage: quote_proof.py verify", "사용법: quote_proof.py verify"))


# ---------- error paths, each in both languages, exit 3 ----------

def expect_error(res, lang, text):
    assert res.code == 3
    assert res.out == ""
    assert res.err.startswith(prefix(lang)), res.err
    assert text in res.err, res.err
    assert (HANGUL.search(res.err) is not None) == (lang == "ko")


@pytest.mark.parametrize("lang", LANGS)
def test_error_report_missing(cli, tmp_path, lang):
    res = cli("verify", "missing-report.md", "--lang", lang)
    expect_error(res, lang, "report file not found: missing-report.md" if lang == "en"
                 else "보고서 파일이 없습니다: missing-report.md")


@pytest.mark.parametrize("lang", LANGS)
def test_error_report_is_a_directory(cli, tmp_path, lang):
    res = cli("verify", str(tmp_path), "--lang", lang)
    expect_error(res, lang, "report file not found" if lang == "en" else "보고서 파일이 없습니다")


@pytest.mark.parametrize("lang", LANGS)
def test_error_report_unreadable(cli, tmp_path, monkeypatch, lang):
    rep = tmp_path / "r.md"
    rep.write_text("x")
    real = Path.read_bytes

    def boom(self):
        if self.name == "r.md":
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", boom)
    res = cli("verify", str(rep), "--lang", lang)
    expect_error(res, lang, "cannot read the report file" if lang == "en" else "보고서 파일을 읽을 수 없습니다")


@pytest.mark.parametrize("lang", LANGS)
def test_error_root_not_a_directory(cli, tmp_path, lang):
    rep = tmp_path / "r.md"
    rep.write_text(f'"{Q}"\n')
    res = cli("verify", str(rep), "--root", "no-such-folder", "--lang", lang)
    expect_error(res, lang, "--root is not a directory: no-such-folder" if lang == "en"
                 else "--root 가 폴더가 아닙니다: no-such-folder")
    res = cli("suggest", str(rep), "--root", str(rep), "--lang", lang)
    assert res.code == 3


@pytest.mark.parametrize("lang", LANGS)
def test_error_report_not_utf8(cli, tmp_path, lang):
    rep = tmp_path / "bad.md"
    rep.write_bytes(b"\xff\xfe broken \x80 bytes")
    res = cli("verify", str(rep), "--lang", lang)
    expect_error(res, lang, "report is not valid UTF-8 text" if lang == "en" else "보고서가 UTF-8 텍스트가 아닙니다")
    assert cli("extract", str(rep), "--lang", lang).code == 3


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("value", ["1.5", "-0.1", "abc", "nan"])
def test_error_min_ratio_out_of_range(cli, sample, lang, value):
    res = cli("verify", str(sample / "report.md"), "--root", str(sample), "--min-ratio", value, "--lang", lang)
    expect_error(res, lang, f"--min-ratio must be between 0 and 1: {value}" if lang == "en"
                 else f"--min-ratio 는 0 과 1 사이여야 합니다: {value}")


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("value", ["0", "-2", "many"])
def test_error_min_words_invalid(cli, sample, lang, value):
    res = cli("extract", str(sample / "report.md"), "--min-words", value, "--lang", lang)
    expect_error(res, lang, f"--min-words must be a whole number of at least 1: {value}" if lang == "en"
                 else f"--min-words 는 1 이상의 정수여야 합니다: {value}")


@pytest.mark.parametrize("env_lang", ["en", "ko"])
def test_error_unsupported_language(cli, sample, monkeypatch, env_lang):
    """The error itself is printed in the language of the environment, English when there is none."""
    monkeypatch.setenv("LANG", "ko_KR.UTF-8" if env_lang == "ko" else "C")
    for argv in (["verify", str(sample / "report.md"), "--lang", "fr"],
                 ["--lang=fr", "verify", str(sample / "report.md")]):
        res = cli(*argv)
        expect_error(res, env_lang, "unsupported language: fr (use en or ko)" if env_lang == "en"
                     else "지원하지 않는 언어입니다: fr (en 또는 ko)")


@pytest.mark.parametrize("lang", LANGS)
def test_error_argparse_usage(cli, sample, lang):
    for argv in (["frobnicate", "x.md"], ["extract"], ["verify", "a.md", "--nope"], ["verify", "a.md", "b.md"], []):
        res = cli(*argv, "--lang", lang)
        assert res.code == 3 and res.out == "", argv
        assert res.err.startswith(prefix(lang)), res.err
        assert ("invalid usage:" in res.err) if lang == "en" else ("사용법이 올바르지 않습니다:" in res.err)


@pytest.mark.parametrize("lang", LANGS)
def test_error_write_overwrite_refusal(cli, sample, lang):
    report = sample / "report.md"
    res = cli("suggest", str(report), "--root", str(sample), "--write", str(report), "--lang", lang)
    expect_error(res, lang, "refusing to overwrite the report; choose another --write path" if lang == "en"
                 else "보고서를 덮어쓰지 않습니다. 다른 --write 경로를 고르세요")


@pytest.mark.parametrize("lang", LANGS)
def test_error_out_overwrite_refusal(cli, sample, lang):
    report = sample / "report.md"
    res = cli("verify", str(report), "--root", str(sample), "--out", str(report), "--lang", lang)
    expect_error(res, lang, "refusing to overwrite the report; choose another --out path" if lang == "en"
                 else "보고서를 덮어쓰지 않습니다. 다른 --out 경로를 고르세요")


@pytest.mark.parametrize("lang", LANGS)
def test_error_no_report_found(cli, tmp_path, monkeypatch, lang):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    for argv in (["verify"], ["verify", "--fix"], ["suggest"]):
        res = cli(*argv, "--lang", lang)
        expect_error(res, lang, "no report given and no Markdown file under . has a quote with a source anchor; "
                                "ask the user which report to check, then pass its path" if lang == "en" else
                     "보고서를 지정하지 않았고 . 아래에 출처를 단 인용이 있는 Markdown 파일이 없습니다. "
                     "확인할 보고서를 사용자에게 물어 경로를 지정하세요")
    assert list(empty.iterdir()) == []      # nothing written


@pytest.mark.parametrize("lang", LANGS)
def test_error_several_reports(cli, sample, lang):
    (sample / "second.md").write_text(f'Also "{Q}" (src/guide.md:1).\n', encoding="utf-8")
    res = cli("verify", "--root", str(sample), "--lang", lang)
    root = qp.clean_path(str(sample))
    paths = f"{root}/report.md, {root}/second.md"
    expect_error(res, lang, f"no report given and several Markdown files under {root} cite sources: {paths}; "
                            "pass the path of the one to check" if lang == "en" else
                 f"보고서를 지정하지 않았고 {root} 아래에 출처를 단 Markdown 파일이 여러 개입니다: {paths}. "
                 "확인할 파일의 경로를 지정하세요")


@pytest.mark.parametrize("lang", LANGS)
def test_picked_report_notice_and_fix_text_are_translated(cli, sample, lang):
    res = cli("verify", "--root", str(sample), "--fix", "--lang", lang)
    assert res.code == 2
    if lang == "en":
        assert res.err.startswith("checking ") and "the only Markdown file here" in res.err
        assert "left to fix by hand in" in res.out and "re-check of the corrected copy" in res.out
    else:
        assert "를 확인합니다" in res.err
        assert "에서 손으로 고칠 것:" in res.out and "다시 확인:" in res.out
        assert "따옴표 없는 바꿔 쓰기로 고치거나 지우세요" in res.out


@pytest.mark.parametrize("lang", LANGS)
def test_error_write_failed(cli, sample, tmp_path, lang):
    res = cli("suggest", str(sample / "report.md"), "--root", str(sample), "--write",
              str(tmp_path / "no" / "such" / "dir" / "out.md"), "--lang", lang)
    assert res.code == 3 and res.err.startswith(prefix(lang))
    assert ("cannot write the file" if lang == "en" else "파일을 쓸 수 없습니다") in res.err


# ---------- warnings (not errors) ----------

@pytest.mark.parametrize("lang", LANGS)
def test_warning_unreadable_source(cli, tree, tmp_path, lang):
    root = tree({"bad.md": b"\xff\xfe broken"})
    rep = tmp_path / "r.md"
    rep.write_text(f'Said "{Q}" (bad.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root), "--lang", lang)
    assert res.code == 2 and res.err == (
        f"{warn_prefix(lang)} " + ("cannot read source: bad.md" if lang == "en" else "원문을 읽을 수 없습니다: bad.md") + "\n")
    data = cli("verify", str(rep), "--root", str(root), "--lang", lang, "--json").json()
    assert data["warnings"] == [{"code": "unreadable", "path": "bad.md"}]


@pytest.mark.parametrize("lang", LANGS)
def test_warning_source_too_large(cli, tree, tmp_path, monkeypatch, lang):
    monkeypatch.setattr(sources, "MAX_SOURCE_BYTES", 50)
    root = tree({"big.md": "x" * 200})
    rep = tmp_path / "r.md"
    rep.write_text(f'Said "{Q}" (big.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root), "--lang", lang)
    assert res.code == 2
    assert ("source is too large (over 5 MB) and was skipped: big.md" if lang == "en"
            else "원문이 너무 커서(5MB 초과) 건너뛰었습니다: big.md") in res.err


@pytest.mark.parametrize("lang", LANGS)
def test_warning_source_outside_root(cli, tree, tmp_path, lang):
    root = tree({"a.md": "x\n"})
    (tmp_path / "other.md").write_text(f"{Q}\n")
    rep = tmp_path / "r.md"
    rep.write_text(f'Said "{Q}" (../other.md:1).\n')
    res = cli("verify", str(rep), "--root", str(root), "--lang", lang)
    assert res.code == 2
    assert ("source is outside --root and was ignored: ../other.md" if lang == "en"
            else "원문이 --root 밖에 있어 무시했습니다: ../other.md") in res.err
    res = cli("verify", str(rep), "--root", str(root), "--source", "../other.md", "--lang", lang)
    assert ("source is outside --root" if lang == "en" else "--root 밖에 있어") in res.err


def test_every_message_key_is_used_somewhere():
    """Dead messages hide untested paths: every key is referenced by the scripts."""
    scripts = Path(qp.__file__).parent
    code = "".join(p.read_text(encoding="utf-8") for p in scripts.glob("*.py") if p.name != "_qp_i18n.py")
    unused = [k for k in i18n.MESSAGES["en"]
              if k not in code and not k.startswith(("help_", "col_", "note_", "unit_", "sg_", "prefix_"))]
    assert unused == []
