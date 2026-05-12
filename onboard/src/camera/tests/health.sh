#!/usr/bin/env bash
set -euo pipefail

# Usage: ./health.sh [API_URL]
API_URL=${1:-http://127.0.0.1:8000}

curl -s ${API_URL}/health | jq || true
