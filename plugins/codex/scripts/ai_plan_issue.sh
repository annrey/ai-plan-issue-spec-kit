#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(CDPATH= cd -- "$PLUGIN_ROOT/../.." && pwd)
TARGET_ROOT=${AI_PLAN_ISSUE_PROJECT_ROOT:-$(pwd)}
PYTHONPATH_ADD=""

PYTHON_BIN=${AI_PLAN_ISSUE_PYTHON:-python3}
if [ -d "$REPO_ROOT/src/ai_plan_issue" ]; then
  PYTHONPATH_ADD="$REPO_ROOT/src"
elif [ -d "$PLUGIN_ROOT/vendor/ai_plan_issue" ]; then
  PYTHONPATH_ADD="$PLUGIN_ROOT/vendor"
fi

cd "$TARGET_ROOT"
if [ "$PYTHONPATH_ADD" != "" ]; then
  PYTHONPATH="$PYTHONPATH_ADD${PYTHONPATH:+:$PYTHONPATH}" exec "$PYTHON_BIN" -m ai_plan_issue.cli "$@"
fi
exec "$PYTHON_BIN" -m ai_plan_issue.cli "$@"
