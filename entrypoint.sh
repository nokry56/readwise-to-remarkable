#!/bin/bash
set -e

RMAPI_CONF_DIR="/root/.config/rmapi"
RMAPI_CONF="${RMAPI_CONF_DIR}/rmapi.conf"
SETTINGS_FILE="/data/settings.json"

# Load settings from persistent file if it exists (web UI saves here)
# These override env vars so changes via web UI stick
if [ -f "$SETTINGS_FILE" ]; then
    echo "Loading saved settings from $SETTINGS_FILE"
    READWISE_TOKEN=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('readwise_token','${READWISE_TOKEN}'))" 2>/dev/null || echo "${READWISE_TOKEN}")
    REMARKABLE_FOLDER=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('remarkable_folder','${REMARKABLE_FOLDER}'))" 2>/dev/null || echo "${REMARKABLE_FOLDER}")
    SYNC_LOCATIONS=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('sync_locations','${SYNC_LOCATIONS}'))" 2>/dev/null || echo "${SYNC_LOCATIONS}")
    SYNC_TAG=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('sync_tag','${SYNC_TAG}'))" 2>/dev/null || echo "${SYNC_TAG}")
    SYNC_INTERVAL=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('sync_interval','${SYNC_INTERVAL}'))" 2>/dev/null || echo "${SYNC_INTERVAL}")
    ECONOMIST_ENABLED=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('economist_enabled','${ECONOMIST_ENABLED:-false}'))" 2>/dev/null || echo "${ECONOMIST_ENABLED:-false}")
    HIGHLIGHT_SYNC_ENABLED=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('highlight_sync_enabled','${HIGHLIGHT_SYNC_ENABLED:-false}'))" 2>/dev/null || echo "${HIGHLIGHT_SYNC_ENABLED:-false}")
fi

# Generate config.cfg from current settings
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
folder = ${ECONOMIST_FOLDER:-Economist}

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
    echo "  rmapi needs authentication."
    echo "  Use the web UI or run:"
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
    cp /app/exported_documents.json /data/exported_documents.json 2>/dev/null || true
    cp "${RMAPI_CONF}" /data/rmapi.conf 2>/dev/null || true
    exit 0
fi

# Start web UI in background
WEBUI_PORT="${WEBUI_PORT:-9080}"
python -u /webui.py &
echo "Web UI started on port ${WEBUI_PORT}"

# Default: loop mode
echo "Starting Readwise-to-reMarkable sync loop"
echo "  Interval: ${SYNC_INTERVAL}s"
echo "  Locations: ${SYNC_LOCATIONS}"
echo "  Tag: ${SYNC_TAG}"
echo "  Folder: ${REMARKABLE_FOLDER}"
echo "  Economist: ${ECONOMIST_ENABLED:-false}"
echo "  Highlight sync: ${HIGHLIGHT_SYNC_ENABLED:-false}"
echo "  Web UI: http://0.0.0.0:${WEBUI_PORT}"
echo ""

SYNC_LOG="/data/sync.log"
# Keep last 2000 lines of log history
truncate_log() {
    if [ -f "$SYNC_LOG" ] && [ "$(wc -l < "$SYNC_LOG")" -gt 2000 ]; then
        tail -1000 "$SYNC_LOG" > "$SYNC_LOG.tmp" && mv "$SYNC_LOG.tmp" "$SYNC_LOG"
    fi
}

# Per-step timeout. A hung sync.py was previously blocking the loop for weeks
# because a child process stayed in a TCP socket wait forever. timeout(1) sends
# SIGTERM at the deadline and SIGKILL 30s later, so the loop can always advance.
SYNC_TIMEOUT="${SYNC_TIMEOUT:-1500}"

while true; do
    echo "--- Sync started at $(date) ---" | tee -a "$SYNC_LOG"

    # Re-read settings before each sync (web UI may have changed them)
    if [ -f "$SETTINGS_FILE" ]; then
        ECONOMIST_ENABLED=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('economist_enabled','false'))" 2>/dev/null || echo "false")
        HIGHLIGHT_SYNC_ENABLED=$(python -c "import json; d=json.load(open('$SETTINGS_FILE')); print(d.get('highlight_sync_enabled','false'))" 2>/dev/null || echo "false")
    fi

    timeout --kill-after=30s "${SYNC_TIMEOUT}s" python -u sync.py 2>&1 | tee -a "$SYNC_LOG"
    rc=${PIPESTATUS[0]}
    if [ "$rc" = "124" ] || [ "$rc" = "137" ]; then
        echo "Sync timed out after ${SYNC_TIMEOUT}s (rc=$rc), will retry next interval" | tee -a "$SYNC_LOG"
    elif [ "$rc" != "0" ]; then
        echo "Sync failed (rc=$rc), will retry next interval" | tee -a "$SYNC_LOG"
    fi

    if [ "${ECONOMIST_ENABLED:-false}" = "true" ]; then
        timeout --kill-after=30s "${SYNC_TIMEOUT}s" python -u economist.py 2>&1 | tee -a "$SYNC_LOG"
        rc=${PIPESTATUS[0]}
        if [ "$rc" = "124" ] || [ "$rc" = "137" ]; then
            echo "Economist sync timed out after ${SYNC_TIMEOUT}s (rc=$rc), will retry next interval" | tee -a "$SYNC_LOG"
        elif [ "$rc" != "0" ]; then
            echo "Economist sync failed (rc=$rc), will retry next interval" | tee -a "$SYNC_LOG"
        fi
    fi

    if [ "${HIGHLIGHT_SYNC_ENABLED:-false}" = "true" ]; then
        timeout --kill-after=30s "${SYNC_TIMEOUT}s" python -u highlights.py 2>&1 | tee -a "$SYNC_LOG"
        rc=${PIPESTATUS[0]}
        if [ "$rc" = "124" ] || [ "$rc" = "137" ]; then
            echo "Highlight sync timed out after ${SYNC_TIMEOUT}s (rc=$rc), will retry next interval" | tee -a "$SYNC_LOG"
        elif [ "$rc" != "0" ]; then
            echo "Highlight sync failed (rc=$rc), will retry next interval" | tee -a "$SYNC_LOG"
        fi
    fi

    # Persist state after each run
    cp /app/exported_documents.json /data/exported_documents.json 2>/dev/null || true
    cp "${RMAPI_CONF}" /data/rmapi.conf 2>/dev/null || true

    echo "--- Next sync in ${SYNC_INTERVAL}s ---" | tee -a "$SYNC_LOG"
    truncate_log
    sleep "${SYNC_INTERVAL}"
done
