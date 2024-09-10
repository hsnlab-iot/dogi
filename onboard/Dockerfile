# Use Ubuntu 20.04 as the base image
FROM ubuntu:latest

# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive

# Update and install GStreamer
RUN apt update && \
    apt install -y --no-install-recommends \
    busybox vim tmux socat \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    supervisor \
    && busybox --install

COPY src/ /root
COPY src/stream_2.sh /usr/local/bin/streamer.sh
RUN chmod +x /usr/local/bin/streamer.sh

COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Set the default command to bash
#CMD ["bash"]
# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
