# Use Ubuntu as the base image
FROM ubuntu:latest

# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive

# Update and install necessary packages
RUN apt update && \
    apt install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    ffmpeg \
    supervisor \
    xvfb tigervnc-standalone-server openbox lxterminal xterm \
    novnc websockify \
    busybox \
    && busybox --install

RUN apt install -y --no-install-recommends \
    socat tmux build-essential git vim python3 python3-pip python3-serial python3-opencv pipx tcpdump \
    && apt clean

RUN pip install ultralytics

RUN apt install -y python3-gst-1.0 libzmq3-dev && \
    pip install zmq

# Copy the supervisor configuration file
COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY src/ /root

# Expose the noVNC port
EXPOSE 6080

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
