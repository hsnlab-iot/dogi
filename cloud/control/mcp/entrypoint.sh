#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="mcp"
MCP_PORT="${MCP_PORT:-5000}"

tmux kill-session -t "${SESSION_NAME}" 2>/dev/null || true
tmux new-session -d -s "${SESSION_NAME}" -n vision \
  "uv run python /app/vision_prompt_mcp_server.py; sleep inf"

echo "Started tmux session '${SESSION_NAME}' with window: vision(:${MCP_PORT})"

sleep inf
