"""English and Korean messages and the language rule. Verdict tokens, JSON keys and the SUMMARY line are not translated."""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional

LANGS = ("en", "ko")
ENV_VAR = "QUOTE_PROOF_LANG"

MESSAGES: Dict[str, Dict[str, str]] = {
    "en": {
        # prefixes
        "prefix_error": "error",
        "prefix_warning": "warning",
        # errors (stderr, exit 3)
        "err_report_missing": "report file not found: {path}",
        "err_report_unreadable": "cannot read the report file: {path}",
        "err_report_not_utf8": "report is not valid UTF-8 text: {path}",
        "err_root_not_dir": "--root is not a directory: {path}",
        "err_min_ratio": "--min-ratio must be between 0 and 1: {value}",
        "err_min_words": "--min-words must be a whole number of at least 1: {value}",
        "err_lang": "unsupported language: {value} (use en or ko)",
        "err_usage": "invalid usage: {detail}",
        "err_write_overwrite": "refusing to overwrite the report; choose another --write path",
        "err_out_overwrite": "refusing to overwrite the report; choose another --out path",
        "err_write_failed": "cannot write the file: {path}",
        "err_no_report": "no report given and no Markdown file under {root} has a quote with a source anchor; "
                         "ask the user which report to check, then pass its path",
        "err_many_reports": "no report given and several Markdown files under {root} cite sources: {paths}; "
                            "pass the path of the one to check",
        # warnings (stderr)
        "warn_unreadable": "cannot read source: {path}",
        "warn_too_large": "source is too large (over 5 MB) and was skipped: {path}; cut it into smaller files or quote from a smaller source",
        "warn_overwrite": "overwriting the existing copy: {path}; hand edits made to it are lost",
        "warn_outside_root": "source is outside --root and was ignored: {path}",
        # notices (stdout)
        "no_quotes": "No quotes found in the report; nothing to verify.",
        "wrote_copy": "wrote the corrected copy: {path}",
        "wrote_out": "wrote the output: {path}",
        "no_suggestions": "Nothing to fix automatically.",
        "picked_report": "checking {path} (the only Markdown file here whose quotes cite a source)",
        "fix_recheck": "re-check of the corrected copy {path}:",
        "todo_header": "left to fix by hand in {path}:",
        "todo_not_found": "{where} not_found: rewrite it as a paraphrase without quotation marks, or remove it; "
                          "do not guess the wording",
        "todo_source_missing": "{where} source_missing: cannot read {path}; fix the path or ask for the file",
        # table headers
        "col_id": "#",
        "col_line": "Line",
        "col_form": "Form",
        "col_verdict": "Verdict",
        "col_source": "Source",
        "col_anchor": "Anchor",
        "col_note": "Note",
        "col_quote": "Quote",
        "col_claimed": "Claimed source",
        # notes
        "note_steps": "ignored: {steps}",
        "note_ratio": "ratio {ratio}, {changed} {unit} changed",
        "note_best_ratio": "closest ratio {ratio}",
        "note_claimed_found": "claimed {claimed}, found {found}",
        "note_claimed_file": "claimed in {claimed}",
        "note_file_missing": "cannot read {path}",
        "note_also_in": "also in {paths}",
        "unit_word": "word(s)",
        "unit_char": "character(s)",
        # suggest
        "sg_anchor": "anchor: {old} -> {new}",
        "sg_quote": "quote: replace with the source text",
        "sg_source": "source {where}",
        # help
        "usage_prefix": "usage: ",
        "help_title_positional": "arguments",
        "help_title_options": "options",
        "help_title_commands": "commands",
        "help_h": "show this help message and exit",
        "help_main": "Check quoted passages and their source anchors in a Markdown report against local source files.",
        "help_epilog": "Exit codes: 0 all quotes exact or normalized; 1 approximate quotes or wrong anchors; "
                       "2 not_found or source_missing; 3 usage or input error.",
        "help_extract": "list the quotes and claimed sources found in the report",
        "help_verify": "check every quote against its source file",
        "help_suggest": "show the exact source text and the right anchor for quotes that can be fixed",
        "help_report": "Markdown report to check",
        "help_report_optional": "Markdown report to check (default: the only Markdown file under --root whose "
                                "quotes cite a source)",
        "help_fix": "also write the corrected copy REPORT.fixed.md, list what is left to fix by hand and re-check "
                    "the copy (exit code of the copy)",
        "help_fix_write": "like --fix, but write the corrected copy to this file",
        "help_root": "folder that anchor paths are relative to (default: current folder)",
        "help_source": "source file to search when a quote has no anchor (repeatable; default: text files under --root)",
        "help_min_ratio": "lowest similarity (0-1) for an approximate match (default: 0.8)",
        "help_min_words": "skip quotes shorter than this many words, CJK: twice as many characters (default: 4)",
        "help_json": "print JSON instead of the table",
        "help_out": "write the output to this file instead of printing it (the SUMMARY line is still printed)",
        "help_write": "write a copy of the report with approximate quotes and wrong anchors fixed",
        "help_lang": "output language: en or ko (also QUOTE_PROOF_LANG, LC_ALL, LC_MESSAGES, LANG)",
        "help_command": "command",
    },
    "ko": {
        "prefix_error": "오류",
        "prefix_warning": "경고",
        "err_report_missing": "보고서 파일이 없습니다: {path}",
        "err_report_unreadable": "보고서 파일을 읽을 수 없습니다: {path}",
        "err_report_not_utf8": "보고서가 UTF-8 텍스트가 아닙니다: {path}",
        "err_root_not_dir": "--root 가 폴더가 아닙니다: {path}",
        "err_min_ratio": "--min-ratio 는 0 과 1 사이여야 합니다: {value}",
        "err_min_words": "--min-words 는 1 이상의 정수여야 합니다: {value}",
        "err_lang": "지원하지 않는 언어입니다: {value} (en 또는 ko)",
        "err_usage": "사용법이 올바르지 않습니다: {detail}",
        "err_write_overwrite": "보고서를 덮어쓰지 않습니다. 다른 --write 경로를 고르세요",
        "err_out_overwrite": "보고서를 덮어쓰지 않습니다. 다른 --out 경로를 고르세요",
        "err_write_failed": "파일을 쓸 수 없습니다: {path}",
        "err_no_report": "보고서를 지정하지 않았고 {root} 아래에 출처를 단 인용이 있는 Markdown 파일이 없습니다. "
                         "확인할 보고서를 사용자에게 물어 경로를 지정하세요",
        "err_many_reports": "보고서를 지정하지 않았고 {root} 아래에 출처를 단 Markdown 파일이 여러 개입니다: {paths}. "
                            "확인할 파일의 경로를 지정하세요",
        "warn_unreadable": "원문을 읽을 수 없습니다: {path}",
        "warn_too_large": "원문이 너무 커서(5MB 초과) 건너뛰었습니다: {path}. 더 작은 파일로 나누거나 더 작은 원문을 인용하세요",
        "warn_overwrite": "기존 사본을 덮어씁니다: {path}. 그 사본에 직접 고친 내용은 사라집니다",
        "warn_outside_root": "원문이 --root 밖에 있어 무시했습니다: {path}",
        "no_quotes": "보고서에서 인용을 찾지 못했습니다. 확인할 것이 없습니다.",
        "wrote_copy": "고친 사본을 썼습니다: {path}",
        "wrote_out": "결과를 파일에 썼습니다: {path}",
        "no_suggestions": "자동으로 고칠 것이 없습니다.",
        "picked_report": "{path} 를 확인합니다 (여기서 출처를 단 인용이 있는 유일한 Markdown 파일)",
        "fix_recheck": "고친 사본 {path} 다시 확인:",
        "todo_header": "{path} 에서 손으로 고칠 것:",
        "todo_not_found": "{where} not_found: 따옴표 없는 바꿔 쓰기로 고치거나 지우세요. 문구를 추측하지 마세요",
        "todo_source_missing": "{where} source_missing: {path} 를 읽을 수 없습니다. 경로를 고치거나 파일을 요청하세요",
        "col_id": "#",
        "col_line": "줄",
        "col_form": "형태",
        "col_verdict": "판정",
        "col_source": "원문 위치",
        "col_anchor": "앵커",
        "col_note": "메모",
        "col_quote": "인용",
        "col_claimed": "주장한 출처",
        "note_steps": "봐준 차이: {steps}",
        "note_ratio": "유사도 {ratio}, {unit} {changed}개 다름",
        "note_best_ratio": "가장 가까운 유사도 {ratio}",
        "note_claimed_found": "주장 {claimed}, 실제 {found}",
        "note_claimed_file": "{claimed} 에 있다고 함",
        "note_file_missing": "{path} 를 읽을 수 없음",
        "note_also_in": "다른 파일에도 있음: {paths}",
        "unit_word": "단어",
        "unit_char": "글자",
        "sg_anchor": "앵커: {old} -> {new}",
        "sg_quote": "인용: 원문 그대로로 바꾸기",
        "sg_source": "원문 {where}",
        "usage_prefix": "사용법: ",
        "help_title_positional": "인자",
        "help_title_options": "옵션",
        "help_title_commands": "명령",
        "help_h": "도움말을 보여 주고 끝냅니다",
        "help_main": "Markdown 보고서의 따옴표 인용과 출처 앵커를 로컬 원문 파일과 대조합니다.",
        "help_epilog": "종료 코드: 0 모두 exact·normalized, 1 approximate 또는 앵커 틀림, "
                       "2 not_found 또는 source_missing, 3 사용법·입력 오류.",
        "help_extract": "보고서에서 찾은 인용과 주장한 출처를 나열합니다",
        "help_verify": "모든 인용을 출처 파일과 대조합니다",
        "help_suggest": "고칠 수 있는 인용의 원문 구간과 올바른 앵커를 보여 줍니다",
        "help_report": "확인할 Markdown 보고서",
        "help_report_optional": "확인할 Markdown 보고서 (기본: --root 아래에서 출처를 단 인용이 있는 유일한 Markdown 파일)",
        "help_fix": "고친 사본 REPORT.fixed.md 도 쓰고, 손으로 고칠 것을 나열한 뒤 사본을 다시 확인합니다 (종료 코드는 사본 기준)",
        "help_fix_write": "--fix 와 같지만 고친 사본을 이 파일에 씁니다",
        "help_root": "앵커 경로의 기준 폴더 (기본: 현재 폴더)",
        "help_source": "앵커 없는 인용을 찾을 원문 파일 (여러 번 가능, 기본: --root 아래 텍스트 파일)",
        "help_min_ratio": "근사 일치로 인정할 최소 유사도(0~1) (기본: 0.8)",
        "help_min_words": "이 단어 수보다 짧은 인용은 건너뜀, 한·중·일은 글자 수 두 배 (기본: 4)",
        "help_json": "표 대신 JSON 으로 출력합니다",
        "help_out": "출력을 화면 대신 이 파일에 씁니다 (SUMMARY 줄은 화면에도 나옵니다)",
        "help_write": "근사 인용과 틀린 앵커를 고친 보고서 사본을 씁니다",
        "help_lang": "출력 언어: en 또는 ko (QUOTE_PROOF_LANG, LC_ALL, LC_MESSAGES, LANG 도 가능)",
        "help_command": "명령",
    },
}


def lang_from_env(env: Optional[Mapping[str, str]] = None) -> str:
    """Language from the environment: QUOTE_PROOF_LANG (en|ko), then the first set of LC_ALL, LC_MESSAGES, LANG.

    A value starting with ``ko`` means Korean; anything else means English.
    """
    env = os.environ if env is None else env
    own = (env.get(ENV_VAR) or "").strip().lower()
    if own in LANGS:
        return own
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (env.get(name) or "").strip().lower()
        if value:
            return "ko" if value.startswith("ko") else "en"
    return "en"


def resolve_lang(cli_value: Optional[str], env: Optional[Mapping[str, str]] = None) -> str:
    """--lang beats QUOTE_PROOF_LANG beats the locale variables. ``cli_value`` must already be valid."""
    if cli_value is not None:
        return cli_value.strip().lower()
    return lang_from_env(env)


def t(lang: str, key: str, **kwargs: object) -> str:
    return MESSAGES[lang][key].format(**kwargs)


def error_text(lang: str, key: str, **kwargs: object) -> str:
    return f"{MESSAGES[lang]['prefix_error']}: {t(lang, key, **kwargs)}"


def warning_text(lang: str, key: str, **kwargs: object) -> str:
    return f"{MESSAGES[lang]['prefix_warning']}: {t(lang, key, **kwargs)}"
