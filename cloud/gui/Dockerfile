# Use Ubuntu as the base image
FROM ubuntu:latest

# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive

# Update and install necessary packages
RUN apt update && \
    apt install -y --no-install-recommends \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    ffmpeg \
    supervisor \
    xfce4 x11vnc xvfb tigervnc-standalone-server openbox lxterminal \
    novnc websockify \
    && apt clean

RUN apt install -y --no-install-recommends \
    build-essential git vim python3 python3-pip pipx

# Copy the supervisor configuration file
COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY src/play.sh /root

# Copy the startup script
COPY src/startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

# Expose the noVNC port
EXPOSE 8080

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
