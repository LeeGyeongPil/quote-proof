"""The version string is the same in every place that states it."""
from __future__ import annotations

import json
import re

import quote_proof as qp
from conftest import REPO


def test_version_is_the_same_everywhere():
    pyproject = re.search(r'^version = "([^"]+)"', (REPO / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    plugin_path = REPO / (".claude" + "-plugin") / "plugin.json"
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))["version"]
    changelog = re.search(r"^## \[(\d[^\]]*)\]", (REPO / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert qp.__version__ == pyproject == plugin == changelog
    lock = (REPO / "uv.lock").read_text(encoding="utf-8")
    assert re.search(r'name = "quote-proof-skill-dev"\nversion = "' + re.escape(pyproject) + '"', lock)
    for readme in ("README.md", "README.ko.md"):
        assert f'"version": "{pyproject}"' in (REPO / readme).read_text(encoding="utf-8")
