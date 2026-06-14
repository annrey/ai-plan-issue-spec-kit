#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EXT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
PROJECT_ROOT=${AI_PLAN_ISSUE_PROJECT_ROOT:-$(pwd)}
PROJECT_ROOT=$(CDPATH= cd -- "$PROJECT_ROOT" && pwd)
SOURCE_ROOT=$(CDPATH= cd -- "$EXT_DIR/../../.." && pwd)

find_python() {
  if [ "${AI_PLAN_ISSUE_PYTHON:-}" != "" ]; then
    printf '%s\n' "$AI_PLAN_ISSUE_PYTHON"
    return 0
  fi

  for candidate in "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/.venv/bin/python3" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

PYTHON_BIN=$(find_python) || {
  echo "ai-plan-issue: no working Python found. Set AI_PLAN_ISSUE_PYTHON=/path/to/python." >&2
  exit 1
}

cd "$PROJECT_ROOT"
export AI_PLAN_ISSUE_DIR="${AI_PLAN_ISSUE_DIR:-.specify/issues}"
if [ -d "$SOURCE_ROOT/src" ]; then
  export PYTHONPATH="$SOURCE_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
fi
exec "$PYTHON_BIN" -m ai_plan_issue.board_server "$@"
