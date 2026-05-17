#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MCP_SSH_PASSWORD:-}" ]]; then
  echo "ERROR: MCP_SSH_PASSWORD environment variable is required"
  exit 1
fi

echo "root:${MCP_SSH_PASSWORD}" | chpasswd
mkdir -p /var/run/sshd

# Run OpenSSH in the background while MCP server stays as PID 1.
/usr/sbin/sshd

# Start MCP servers in tmux so multiple servers can run side-by-side.
SESSION_NAME="mcp"
BODY_MCP_PORT="${MCP_PORT:-5000}"
MEMORY_MCP_PORT="${MCP_MEMORY_PORT:-5001}"

# Clear stale session if container restarts in-place.
tmux kill-session -t "${SESSION_NAME}" 2>/dev/null || true

tmux new-session -d -s "${SESSION_NAME}" -n body \
  "uv run python /app/body_mcp_server.py; sleep inf"

tmux new-window -t "${SESSION_NAME}" -n memory \
  "uv run fastmcp run /app/mcp_memory.py:mcp --transport streamable-http --host 0.0.0.0 --port ${MEMORY_MCP_PORT}; sleep inf"

echo "Started tmux session '${SESSION_NAME}' with windows: body(:${BODY_MCP_PORT}), memory(:${MEMORY_MCP_PORT})"

sleep inf
