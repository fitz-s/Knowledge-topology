#!/usr/bin/env bash
set -euo pipefail

if [ -z "${CLAUDE_PROJECT_DIR:-}" ]; then
  echo "CLAUDE_PROJECT_DIR is required for topology guard" >&2
  exit 2
fi

PYTHONPATH="$CLAUDE_PROJECT_DIR/src" \
  python3 -m knowledge_topology.cli agent-guard claude-pre-tool-use \
  --root "$CLAUDE_PROJECT_DIR"
