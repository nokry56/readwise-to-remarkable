#!/bin/bash
set -e

RMAPI_CONF_DIR="/root/.config/rmapi"
RMAPI_CONF="${RMAPI_CONF_DIR}/rmapi.conf"

# Generate config.cfg from environment variables
cat > /app/config.cfg <<EOF
[readwise]
access_token = ${READWISE_TOKEN}

[remarkable]
rmapi_path = rmapi
folder = ${REMARKABLE_FOLDER}

[sync]
locations = ${SYNC_LOCATIONS}
tag = ${SYNC_TAG}

[economist]
enabled = ${ECONOMIST_ENABLED:-false}

[highlights]
enabled = ${HIGHLIGHT_SYNC_ENABLED:-false}
EOF

# Restore rmapi auth from persistent storage
mkdir -p "${RMAPI_CONF_DIR}"
if [ -f /data/rmapi.conf ]; then
    cp /data/rmapi.conf "${RMAPI_CONF}"
    echo "Restored rmapi auth from persistent storage."
else
    echo "============================================"
    echo "  rmapi needs one-time authentication."
    echo "  Run this container interactively first:"
    echo ""
    echo "    docker exec -it readwise-remarkable rmapi ls"
    echo ""
    echo "  Then follow the device code auth flow."
    echo "============================================"
fi

# Restore export tracker from persistent storage
if [ -f /data/exported_documents.json ]; then
    cp /data/exported_documents.json /app/exported_documents.json 2>/dev/null || true
fi

# If first argument is "rmapi", run rmapi for auth setup
if [ "$1" = "rmapi" ]; then
    echo "Starting rmapi for authentication..."
    echo "Follow the instructions to authenticate with your reMarkable account."
    rmapi
    # Save auth token to persistent storage
    cp "${RMAPI_CONF}" /data/rmapi.conf 2>/dev/null || true
    echo "Auth saved! You can now run the container normally."
    exit 0
fi

# If first argument is "once", run sync once and exit
if [ "$1" = "once" ]; then
    echo "Running single sync..."
    python -u sync.py
    if [ "${ECONOMIST_ENABLED:-false}" = "true" ]; then
        python -u economist.py
    fi
    if [ "${HIGHLIGHT_SYNC_ENABLED:-false}" = "true" ]; then
        python -u highlights.py
    fi
    # Persist state
    cp /app/exported_documents.json /data/exported_documents.json 2>/dev/null || true
    cp "${RMAPI_CONF}" /data/rmapi.conf 2>/dev/null || true
    exit 0
fi

# Default: loop mode
echo "Starting Readwise-to-reMarkable sync loop"
echo "  Interval: ${SYNC_INTERVAL}s"
echo "  Locations: ${SYNC_LOCATIONS}"
echo "  Tag: ${SYNC_TAG}"
echo "  Folder: ${REMARKABLE_FOLDER}"
echo "  Economist: ${ECONOMIST_ENABLED:-false}"
echo "  Highlight sync: ${HIGHLIGHT_SYNC_ENABLED:-false}"
echo ""

while true; do
    echo "--- Sync started at $(date) ---"
    python -u sync.py || echo "Sync failed, will retry next interval"

    # Run Economist sync if enabled
    if [ "${ECONOMIST_ENABLED:-false}" = "true" ]; then
        python -u economist.py || echo "Economist sync failed, will retry next interval"
    fi

    # Run highlight sync if enabled
    if [ "${HIGHLIGHT_SYNC_ENABLED:-false}" = "true" ]; then
        python -u highlights.py || echo "Highlight sync failed, will retry next interval"
    fi

    # Persist state after each run
    cp /app/exported_documents.json /data/exported_documents.json 2>/dev/null || true
    cp "${RMAPI_CONF}" /data/rmapi.conf 2>/dev/null || true

    echo "--- Next sync in ${SYNC_INTERVAL}s ---"
    sleep "${SYNC_INTERVAL}"
done
