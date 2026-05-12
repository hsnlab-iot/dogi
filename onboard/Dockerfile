ARG UBUNTU_VERSION=24.04

# STAGE 1: Builder
FROM ubuntu:${UBUNTU_VERSION} AS builder

# Install Python and uv
# We need curl to get uv, and python3-venv to create the environment
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    build-essential \
    curl \
    python3-dev pkg-config libcairo2-dev libgirepository1.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv binary directly from the official installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Prevent uv from complaining about missing git/etc if not needed
ENV UV_HTTP_TIMEOUT=100

# Copy only the requirements file first for better caching
COPY src/camera/requirements.txt .

# Create the venv and install dependencies
# We use --prefix or just a standard .venv folder
RUN uv venv .venv && \
    uv pip install -r requirements.txt

# STAGE 2: Runtime
FROM ubuntu:${UBUNTU_VERSION}

# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive

# Update and install GStreamer
RUN apt update && \
    apt install -y --no-install-recommends \
    busybox vim tmux socat v4l-utils \
    python3 libcairo2 \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-tools \
    libgirepository-1.0-1 gobject-introspection \
    python3-gi gir1.2-gst-rtsp-server-1.0 gir1.2-gstreamer-1.0 \
    supervisor \
    && busybox --install

COPY --from=builder /app/.venv /root/.venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY src/ /root

ENV PATH="/root/.venv/bin:${PATH}"

COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Set the default command to bash
#CMD ["bash"]

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]