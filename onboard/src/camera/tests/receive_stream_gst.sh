#!/usr/bin/env bash
set -euo pipefail

# Usage: ./receive_stream_gst.sh [PORT]
PORT=${1:-5000}

echo "Listening for UDP H264 stream on port ${PORT} (press Ctrl-C to stop)"
# This requires GStreamer installed on the system
gst-launch-1.0 -v udpsrc port=${PORT} caps="application/x-rtp,media=video,encoding-name=H264,payload=96" ! rtph264depay ! avdec_h264 ! autovideosink
