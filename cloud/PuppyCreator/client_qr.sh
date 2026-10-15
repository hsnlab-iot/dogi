#!/usr/bin/env bash

PORT=8888

echo "Starting local Python HTTP server on port $PORT..."
python3 -m http.server $PORT &
SERVER_PID=$!

cleanup() {
  echo ""
  echo "Shutting down Python server (PID $SERVER_PID)..."
  kill $SERVER_PID 2>/dev/null
  exit 0
}

trap cleanup INT TERM

echo "Initializing Pinggy SSH tunnel with QR Code..."
echo "------------------------------------------------"

# Adding pseudo-terminal allocation (-t) forces Pinggy to render the ASCII QR code
ssh -t -p 443 -R0:localhost:$PORT qr@a.pinggy.io

cleanup