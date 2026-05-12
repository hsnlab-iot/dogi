#!/usr/bin/env bash
set -euo pipefail

# Usage: ./snapshot.sh [API_URL] [OUT_FILE]
API_URL=${1:-http://127.0.0.1:8000}
OUT_FILE=${2:-snapshot.jpg}

echo "Requesting snapshot from ${API_URL}/snapshot -> ${OUT_FILE}"
curl -s ${API_URL}/snapshot --output ${OUT_FILE} || { echo "snapshot failed"; exit 1; }
echo "Saved ${OUT_FILE} (size=$(stat -c%s "${OUT_FILE}" 2>/dev/null || echo 0) bytes)"
