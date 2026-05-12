#!/usr/bin/env bash
set -euo pipefail

# Usage: ./start_stream.sh [STREAM_HOST] [STREAM_PORT] [API_URL]
STREAM_HOST=${1:-127.0.0.1}
STREAM_PORT=${2:-5000}
API_URL=${3:-http://127.0.0.1:8000}

curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"address\": \"${STREAM_HOST}\", \"port\": ${STREAM_PORT}}" \
  ${API_URL}/start_stream | jq || true

echo "requested stream to ${STREAM_HOST}:${STREAM_PORT} via ${API_URL}/start_stream"
