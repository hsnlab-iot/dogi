# Use Ubuntu as the base image
FROM dogi-base:latest


# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    VIRTUAL_ENV=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN \
  echo "nvidia-cudnn-cu12==9.1.0.70" > overrides.txt && \
  echo "nvidia-cublas-cu12==12.1.3.1" >> overrides.txt

RUN \
  uv venv && \
  uv pip install  mcp python-socketio[client] && \
  uv pip install  arize-phoenix-otel openinference-instrumentation-openai openai && \
  uv pip install  boltons gevent gevent-websocket ujson websockets wsproto

RUN \
  uv pip install f5-tts torch torchaudio \
    --extra-index-url https://download.pytorch.org/whl/cu124 \
    --override overrides.txt

# Copy the supervisor configuration file
COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

COPY src/ /app
# Expose the noVNC port
EXPOSE 6080
EXPOSE 5050

CMD ["/usr/bin/bash", "-c", "/usr/local/bin/docker-entrypoint.sh"]
