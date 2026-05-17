#!/bin/bash

# --- CONFIGURATION ---
TARGET_DIR="/home/pi/dogi/onboard"
COMPOSE_FILE="$TARGET_DIR/docker-compose.yaml"

echo "Dogi: Starting Docker Restart Sequence..."

# 1. Enter the target directory
cd "$TARGET_DIR" || { echo "ERROR: Path $TARGET_DIR not found"; exit 1; }

# 2. Check if the Compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: docker-compose.yaml not found in $TARGET_DIR"
    exit 1
fi

# 3. Clean up existing containers
# 'down' stops containers and removes networks/orphans
echo "Dogi: Cleaning up old containers..."
docker compose down --remove-orphans

# 4. Start the new session
echo "Dogi: Launching Docker Compose..."
if docker compose up -d; then
    echo "Dogi: SUCCESS. Docker containers are running."
else
    echo "ERROR: Docker Compose failed to start."
    exit 1
fi

# 5. Brief status check
docker compose ps
