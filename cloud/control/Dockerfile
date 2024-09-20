# Use Ubuntu as the base image
FROM ubuntu:24.04

# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive

# Update and install necessary packages
RUN apt update && \
    apt install -y \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    ffmpeg \
    xvfb tigervnc-standalone-server openbox lxterminal xterm \
    novnc websockify \
    busybox socat tmux build-essential git vim tcpdump software-properties-common curl \
    python3 python3-pip python3-serial python3-opencv pipx python3-dev python3-gst-1.0 \
    python3-zmq libzmq3-dev \
    && busybox --install

SHELL ["/bin/bash", "-c"]
RUN \
    cd /root && \
    python3 -m venv .yolo && source /root/.yolo/bin/activate && \ 
    pip install --upgrade pip && \
    pip install --break-system-packages --retries 20 ultralytics pyzmq && \
    deactivate

RUN \
    cd /root && \
    python3 -m venv .flask && source /root/.flask/bin/activate && \ 
    pip install flask flask-socketio && \
    deactivate

# Wprkaround for supervisord (missing symbol)
RUN \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt install -y python3.9 python3.9-distutils && \
    pipx install supervisor --python /usr/bin/python3.9

# Copy the supervisor configuration file
COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

COPY src/ /root

# Expose the noVNC port
EXPOSE 6080
EXPOSE 5050

# Start supervisord
#CMD ["python3.9", "/usr/local/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
CMD ["/usr/bin/bash", "-c", "/usr/local/bin/docker-entrypoint.sh"]
