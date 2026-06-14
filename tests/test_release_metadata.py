from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 test environment.
    import tomli as tomllib

import ai_plan_issue


RELEASE_VERSION = "1.1.0"


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


def test_python_package_includes_board_assets() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["ai_plan_issue"]

    assert "web/index.html" in package_data
    assert "web/app.js" in package_data
    assert "web/styles.css" in package_data


def test_python_package_uses_modern_license_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]


def test_codex_plugin_release_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    plugin_root = root / "plugins" / "codex"
    manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    skill = (plugin_root / "skills" / "ai-plan-issue" / "SKILL.md").read_text(encoding="utf-8")

    assert manifest["name"] == "ai-plan-issue"
    for path in (
        ".codex-plugin/plugin.json",
        "README.md",
        "scripts/ai_plan_issue.sh",
        "scripts/board_server.sh",
        "skills/ai-plan-issue/SKILL.md",
        "vendor/ai_plan_issue/cli.py",
        "vendor/ai_plan_issue/board_server.py",
        "vendor/ai_plan_issue/context_bundle.py",
        "vendor/ai_plan_issue/web/index.html",
        "vendor/ai_plan_issue/web/app.js",
        "vendor/ai_plan_issue/web/styles.css",
    ):
        assert (plugin_root / path).is_file()

    for required in ("context", "claim", "run", "note", "status", "comment"):
        assert required in skill
