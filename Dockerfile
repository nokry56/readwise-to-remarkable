FROM python:3.12-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    cron \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install rmapi (reMarkable cloud API tool)
ARG RMAPI_VERSION=0.0.32
RUN curl -fsSL "https://github.com/ddvk/rmapi/releases/download/v${RMAPI_VERSION}/rmapi-linux-amd64.tar.gz" \
    -o /tmp/rmapi.tar.gz \
    && tar xzf /tmp/rmapi.tar.gz -C /usr/local/bin/ \
    && chmod +x /usr/local/bin/rmapi \
    && rm /tmp/rmapi.tar.gz

WORKDIR /app

# Clone the repo and install Python deps
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git clone https://github.com/nokry56/readwise-to-remarkable-fork.git . \
    && apt-get purge -y git && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

# Create directories for persistent data and rmapi config
RUN mkdir -p /data /root/.config/rmapi

ENV PYTHONUNBUFFERED=1

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default sync interval: 30 minutes (in seconds)
ENV SYNC_INTERVAL=1800
ENV READWISE_TOKEN=""
ENV REMARKABLE_FOLDER="Readwise"
ENV SYNC_LOCATIONS="new,later,shortlist"
ENV SYNC_TAG="remarkable"
ENV ECONOMIST_ENABLED="false"

VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
