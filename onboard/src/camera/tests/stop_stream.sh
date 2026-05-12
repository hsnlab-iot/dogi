#!/usr/bin/env bash
set -euo pipefail

# Usage: ./stop_stream.sh [API_URL]
API_URL=${1:-http://127.0.0.1:8000}

curl -s -X POST ${API_URL}/stop_stream | jq || true
echo "requested stop_stream via ${API_URL}/stop_stream"
