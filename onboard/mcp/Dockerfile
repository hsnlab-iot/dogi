FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    curl \
    ca-certificates \
    openssh-server \
    tmux \
    && rm -rf /var/lib/apt/lists/*

# Install uv from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY mcp/requirements.txt /app/mcp/requirements.txt
RUN uv venv /opt/venv && uv pip install -r /app/mcp/requirements.txt

COPY mcp/app /app

# Configure OpenSSH for password login.
RUN sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/^#\?UsePAM .*/UsePAM no/' /etc/ssh/sshd_config

COPY mcp/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 22 5000

ENTRYPOINT ["/app/entrypoint.sh"]
