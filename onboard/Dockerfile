# Use Ubuntu 20.04 as the base image
FROM ubuntu:latest

# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive

# Update and install GStreamer
RUN apt update && \
    apt install -y --no-install-recommends \
    busybox vim tmux socat v4l-utils build-essential \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-tools \
    libgirepository1.0-dev gobject-introspection \
    python3-gi gir1.2-gst-rtsp-server-1.0 gir1.2-gstreamer-1.0 \
    supervisor \
    libcairo2-dev pkg-config python3-dev \
    python3-gi python3-numpy python3-psutil python3-tomli python3-pydantic \
    && busybox --install

RUN apt install -y --no-install-recommends \
    python3-gi python3-numpy python3-psutil python3-tomli python3-pydantic

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvbin/uv
ENV PATH="/uvbin:${PATH}"

COPY src/ /root
#COPY src/stream_5.sh /usr/local/bin/streamer.sh
#RUN chmod +x /usr/local/bin/streamer.sh

COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Set the default command to bash
#CMD ["bash"]
# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
