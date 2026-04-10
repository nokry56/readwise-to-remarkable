#!/bin/bash
set -e

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
EOF

# Symlink rmapi config to persistent storage so auth survives restarts
if [ ! -f /data/.rmapi ]; then
    # First run - rmapi needs auth
    echo "============================================"
    echo "  rmapi needs one-time authentication."
    echo "  Run this container interactively first:"
    echo ""
    echo "    docker run -it --rm -v rmapi_data:/data readwise-remarkable rmapi"
    echo ""
    echo "  Then follow the device code auth flow."
    echo "============================================"
fi

# Link rmapi config from persistent volume
if [ -f /data/.rmapi ]; then
    cp /data/.rmapi /root/.rmapi
fi

# Symlink exported tracker to persistent storage
if [ -f /data/exported_documents.json ]; then
    cp /data/exported_documents.json /app/exported_documents.json 2>/dev/null || true
fi

# If first argument is "rmapi", run rmapi for auth setup
if [ "$1" = "rmapi" ]; then
    echo "Starting rmapi for authentication..."
    echo "Follow the instructions to authenticate with your reMarkable account."
    rmapi
    # Save auth token to persistent storage
    cp /root/.rmapi /data/.rmapi 2>/dev/null || true
    echo "Auth saved! You can now run the container normally."
    exit 0
fi

# If first argument is "once", run sync once and exit
if [ "$1" = "once" ]; then
    echo "Running single sync..."
    python sync.py
    # Persist tracker
    cp /app/exported_documents.json /data/exported_documents.json 2>/dev/null || true
    cp /root/.rmapi /data/.rmapi 2>/dev/null || true
    exit 0
fi

# Default: loop mode
echo "Starting Readwise-to-reMarkable sync loop"
echo "  Interval: ${SYNC_INTERVAL}s"
echo "  Locations: ${SYNC_LOCATIONS}"
echo "  Tag: ${SYNC_TAG}"
echo "  Folder: ${REMARKABLE_FOLDER}"
echo ""

while true; do
    echo "--- Sync started at $(date) ---"
    python sync.py || echo "Sync failed, will retry next interval"

    # Persist state after each run
    cp /app/exported_documents.json /data/exported_documents.json 2>/dev/null || true
    cp /root/.rmapi /data/.rmapi 2>/dev/null || true

    echo "--- Next sync in ${SYNC_INTERVAL}s ---"
    sleep "${SYNC_INTERVAL}"
done
