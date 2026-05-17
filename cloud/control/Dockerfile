# Use Ubuntu as the base image
FROM dogi-base:latest


# Set non-interactive mode for APT
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8

RUN \
  /opt/venv/bin/pip install mcp python-socketio[client] && \
  /opt/venv/bin/pip install arize-phoenix-otel openinference-instrumentation-openai openai

# Copy the supervisor configuration file
COPY src/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

COPY src/ /app
# Expose the noVNC port
EXPOSE 6080
EXPOSE 5050

CMD ["/usr/bin/bash", "-c", "/usr/local/bin/docker-entrypoint.sh"]
