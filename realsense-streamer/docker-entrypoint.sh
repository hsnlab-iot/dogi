#!/bin/bash

#/usr/local/bin/overlay.sh

echo "/home/pi/librealsense.ro/build/Release" | tee /etc/ld.so.conf.d/librealsense.conf
ldconfig

source /opt/venv311/bin/activate && \
  cp /home/pi/librealsense.ro/build/Release/pyrealsense2.cpython-311-aarch64-linux-gnu.so \
  $(python3 -c "import site; print(site.getsitepackages()[0])") && \
  deactivate

if [ -n "$REPLAY_FILE" ]; then
  tmux new-session -d -s replay "python3 /opt/ws/src/ros2_rs_video/src/video_compression/video_compression/replay.py /opt/local/$REPLAY_FILE; sleep inf"
else
  tmux new-session -d -s streamer "source /opt/venv311/bin/activate && python3.11 /opt/ws/src/ros2_rs_video/src/video_compression/video_compression/rs_streamer.py; sleep inf"
fi

tmux new-session -d -s compress "source /opt/ws/install/setup.bash && ros2 launch /opt/ws/launch/compress.launch.py; sleep inf"

tail -f /dev/null
