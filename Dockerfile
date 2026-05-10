FROM python:3.12-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    cron \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install rmapi (reMarkable cloud API tool)
# v0.0.33 added support for reMarkable cloud schema v4 — older versions
# fail with HTTP 400 on uploads against the current cloud.
ARG RMAPI_VERSION=0.0.33
RUN curl -fsSL "https://github.com/ddvk/rmapi/releases/download/v${RMAPI_VERSION}/rmapi-linux-amd64.tar.gz" \
    -o /tmp/rmapi.tar.gz \
    && tar xzf /tmp/rmapi.tar.gz -C /usr/local/bin/ \
    && chmod +x /usr/local/bin/rmapi \
    && rm /tmp/rmapi.tar.gz

WORKDIR /app

# Clone the repo and install Python deps
# CACHEBUST ensures fresh clone on every build (set by GitHub Actions)
ARG CACHEBUST=1
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git clone https://github.com/nokry56/readwise-to-remarkable-fork.git . \
    && apt-get purge -y git && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

# Create directories for persistent data and rmapi config
RUN mkdir -p /data /root/.config/rmapi

ENV PYTHONUNBUFFERED=1

# Web UI (Docker-only, not in upstream fork)
COPY webui.py /webui.py

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default settings
ENV SYNC_INTERVAL=1800
ENV READWISE_TOKEN=""
ENV REMARKABLE_FOLDER="Readwise"
ENV SYNC_LOCATIONS="new,later,shortlist,feed"
ENV SYNC_TAG="*"
ENV ECONOMIST_ENABLED="true"
ENV HIGHLIGHT_SYNC_ENABLED="true"
ENV WEBUI_PORT=9080

EXPOSE 9080

VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
