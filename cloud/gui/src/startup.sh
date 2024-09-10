#!/bin/bash
# Start the Xvfb server
Xvfb :0 -screen 0 1024x768x24 &

# Start the x11vnc server
x11vnc -display :0 -forever -nopw -create &

# Start the noVNC server
websockify --web=/usr/share/novnc/ 8080 localhost:5900 &
