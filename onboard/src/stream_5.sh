#!/usr/bin/bash

gst-launch-1.0 v4l2src device=/dev/video4 ! \
    video/x-raw,width=640,height=480,framerate=30/1,format=YUY2 ! \
    videoconvert ! \
    x264enc tune=zerolatency bitrate=2000 speed-preset=superfast key-int-max=60 ! \
    rtph264pay config-interval=1 mtu=1240 ! \
    udpsink host=${VIDEO_DST} port=${VIDEO_PORT}
