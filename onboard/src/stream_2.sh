#!/usr/bin/bash

gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! x264enc tune=zerolatency bitrate=2000 speed-preset=superfast b-adapt=false key-int-max=3 sliced-threads=true ! video/x-h264,profile=main,stream-format=byte-stream, alignement=nal ! h264parse ! rtph264pay config-interval=1 ! udpsink host=${VIDEO_DST} port=${VIDEO_PORT}
