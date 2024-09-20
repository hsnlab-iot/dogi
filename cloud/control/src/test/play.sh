gst-launch-1.0 udpsrc port=5100 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=H264" ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! autovideosink
