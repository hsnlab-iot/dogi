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

# Serve FastMCP over HTTP on port 5000.
exec fastmcp run /app/mcp_memory.py:mcp --transport http --host 0.0.0.0 --port 5000
