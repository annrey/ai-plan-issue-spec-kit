#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH= cd -- "$PLUGIN_ROOT/../.." && pwd)
TARGET_ROOT=${AI_PLAN_ISSUE_PROJECT_ROOT:-$(pwd)}

PYTHON_BIN=${AI_PLAN_ISSUE_PYTHON:-python3}
cd "$TARGET_ROOT"
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PYTHON_BIN" -m ai_plan_issue.cli "$@"
