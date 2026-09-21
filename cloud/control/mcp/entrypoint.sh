#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="mcp"
MCP_PORT="${MCP_PORT:-5000}"
TODOS_PORT="${TODOS_PORT:-5001}"

tmux kill-session -t "${SESSION_NAME}" 2>/dev/null || true
tmux new-session -d -s "${SESSION_NAME}" -n vision \
  "uv run python /app/vision_prompt_mcp_server.py; sleep inf"
tmux new-window -t "${SESSION_NAME}" -n todos \
  "uv run python /app/todos_mcp_server.py; sleep inf"

echo "Started tmux session '${SESSION_NAME}' with windows: vision(:${MCP_PORT}), todos(:${TODOS_PORT})"

sleep inf
