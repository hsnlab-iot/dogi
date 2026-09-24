#!/bin/bash

# 1. Get the absolute path of the directory where THIS script lives
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SESSION_NAME="BLE"
VENV_PATH="$SCRIPT_DIR/venv/bin/activate"

echo "Dogi: Detected script directory: $SCRIPT_DIR"

# 2. Enter the directory
cd "$SCRIPT_DIR" || exit

# 3. Clean up any frozen or existing session with the same name
tmux kill-session -t "$SESSION_NAME" 2>/dev/null

# 4. Start the tmux session in the background (-d)
tmux new-session -d -s "$SESSION_NAME"

# 5. Send the execution string to the session
# We use full paths for the venv to ensure no "File not found" errors
tmux send-keys -t "$SESSION_NAME" "source $VENV_PATH" C-m
tmux send-keys -t "$SESSION_NAME" "python3 server-noise.py" C-m

echo "Dogi: $SESSION_NAME session started successfully."