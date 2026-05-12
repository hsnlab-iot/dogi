#!/bin/bash

# Configuration
BASE_URL="http://localhost:8000/mcp"
LISTENER_LOG="sse_output.log"

echo "1. Connecting to SSE to get Session ID and Endpoint..."

# Start the listener in the background and save output to a file
# -N (no buffer), -s (silent)
curl -s -N "$BASE_URL/sse" > "$LISTENER_LOG" &
CURL_PID=$!

# Wait for the session to initialize and provide the endpoint
sleep 2

# Extract the endpoint URL from the SSE log
# MCP SSE usually sends an 'endpoint' event containing the /messages URL with the session_id
MESSAGE_URL=$(grep -oP '(?<=endpoint=).*' "$LISTENER_LOG" | tail -n 1)

# Fallback: If grep -oP fails, we try to construct it manually from the log
if [ -z "$MESSAGE_URL" ]; then
    SESSION_ID=$(grep -oP '(?<=session_id=)[^& \n]*' "$LISTENER_LOG" | tail -n 1)
    if [ -n "$SESSION_ID" ]; then
        MESSAGE_URL="$BASE_URL/messages/?session_id=$SESSION_ID"
    fi
fi

if [ -z "$MESSAGE_URL" ]; then
    echo "Error: Could not retrieve Session ID from SSE stream."
    kill $CURL_PID
    exit 1
fi

echo "Successfully connected!"
echo "Endpoint: $MESSAGE_URL"
echo "-----------------------------------"

echo "2. Sending 'tools/list' request..."
curl -s -X POST "$MESSAGES_URL" \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/list",
       "params": {}
     }' | jq . || echo "Check log for raw response"

echo -e "\n3. Sending 'get_snapshot' request..."
curl -s -X POST "$MESSAGES_URL" \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": 2,
       "method": "tools/call",
       "params": {
         "name": "get_snapshot",
         "arguments": {}
       }
     }' | jq . || echo "Check log for raw response"


echo -e "\n\n4. Checking SSE log for results..."
sleep 1
tail -n 20 "$LISTENER_LOG"

# Clean up
kill $CURL_PID
#rm "$LISTENER_LOG"
