from __future__ import annotations

import json
import re
from pathlib import Path

import ai_plan_issue


RELEASE_VERSION = "1.0.1"


def test_release_versions_are_aligned() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    plugin_manifest = json.loads((root / "plugins" / "codex" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    vendor_init = (root / "plugins" / "codex" / "vendor" / "ai_plan_issue" / "__init__.py").read_text(encoding="utf-8")
    pyproject_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert pyproject_version
    assert pyproject_version.group(1) == RELEASE_VERSION
    assert ai_plan_issue.__version__ == RELEASE_VERSION
    assert plugin_manifest["version"] == RELEASE_VERSION
    assert f'__version__ = "{RELEASE_VERSION}"' in vendor_init
