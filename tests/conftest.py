"""Shared helpers: run the CLI in-process, build small source trees, keep the locale out of the tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import quote_proof as qp

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "sample"


@pytest.fixture(autouse=True)
def _english_by_default(monkeypatch):
    """Tests must not depend on the developer's locale."""
    for name in ("QUOTE_PROOF_LANG", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "C")


class Result:
    def __init__(self, code: int, out: str, err: str):
        self.code, self.out, self.err = code, out, err

    @property
    def summary(self) -> str:
        return self.out.rstrip("\n").split("\n")[-1]

    def json(self) -> dict:
        return json.loads(self.out)


@pytest.fixture
def cli(capsys):
    """cli('verify', 'report.md', '--root', 'x') runs quote_proof.main and returns Result(code, out, err)."""

    def run(*argv: str) -> Result:
        code = qp.main(list(argv))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return run


@pytest.fixture
def sample(tmp_path) -> Path:
    """A private copy of sample/ so tests can write next to it."""
    dest = tmp_path / "sample"
    shutil.copytree(SAMPLE, dest, ignore=shutil.ignore_patterns("*.fixed.md"))
    return dest


@pytest.fixture
def tree(tmp_path):
    """tree({'a.md': 'text', ...}) writes files below tmp_path/docs and returns that folder."""

    def make(files: dict, folder: str = "docs") -> Path:
        base = tmp_path / folder
        for name, content in files.items():
            p = base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_bytes(content.encode("utf-8"))
        return base

    return make
