# Readwise-to-reMarkable Docker

Syncs Readwise Reader articles to your reMarkable tablet. Unseen documents from configured locations auto-upload as EPUBs/PDFs via [rmapi](https://github.com/ddvk/rmapi). Archived or seen items are automatically removed from reMarkable.

Includes a **web UI** for managing all settings and rmapi authentication — no SSH required.

Based on [donmerendolo/readwise-to-remarkable](https://github.com/donmerendolo/readwise-to-remarkable).

## Features

- **Web UI** for settings management and rmapi authentication (port 8080)
- **Sync unseen documents** from Readwise Reader to reMarkable
- **Auto-cleanup**: documents that are archived, seen, or deleted in Reader are removed from reMarkable
- **Economist sync**: weekly PDF from [evanbio/The_Economist](https://github.com/evanbio/The_Economist), saved to Readwise Reader
- **Highlight sync**: highlights made on reMarkable are synced back to Readwise (EPUBs and PDFs)
- PDFs downloaded directly, articles converted to EPUB
- Persistent settings — changes via web UI survive container restarts

## Unraid Setup

### 1. Add template repository

In Unraid web UI:
1. Go to **Apps** tab (requires Community Applications plugin)
2. Click the **gear icon** (settings) at bottom-left
3. Under **Template Repositories**, add:
   ```
   https://github.com/nokry56/unraid-templates
   ```
4. Click **Save**

### 2. Install from Apps tab

1. Go to **Apps** tab, search "readwise"
2. Click **Install**
3. Click **Apply** (defaults are fine — you'll configure via web UI)

### 3. Configure via web UI

1. Open the web UI (click the container icon in Unraid, or go to `http://tower:8080`)
2. Enter your **Readwise Token** (get it from https://readwise.io/access_token)
3. Click **Start reMarkable Authentication** and follow the device code flow
4. Adjust sync settings as needed
5. Click **Save Settings**

All settings persist to `/data/settings.json` and survive container restarts. You can change settings at any time via the web UI without rebuilding the container.

## Environment Variables

Environment variables provide initial defaults. Settings changed via the web UI override these.

| Variable | Default | Description |
|---|---|---|
| `READWISE_TOKEN` | *(empty)* | Your Readwise access token |
| `REMARKABLE_FOLDER` | `Readwise` | Folder on reMarkable for uploads |
| `SYNC_LOCATIONS` | `new,later,shortlist,feed` | Readwise locations to sync from |
| `SYNC_TAG` | `*` | Tag to filter documents by (`*` for all) |
| `SYNC_INTERVAL` | `1800` | Seconds between sync runs (30 min) |
| `ECONOMIST_ENABLED` | `false` | Enable weekly Economist PDF sync to Readwise |
| `HIGHLIGHT_SYNC_ENABLED` | `false` | Sync highlights from reMarkable back to Readwise |
| `WEBUI_PORT` | `8080` | Port for the settings web UI |

## How It Works

### Web UI
A lightweight settings panel runs on port 8080 (configurable). Edit any setting, trigger manual syncs, and authenticate rmapi — all from your browser. Settings are saved to `/data/settings.json` and re-read before each sync cycle.

### Sync logic
1. Fetches unseen documents from configured Readwise locations
2. Converts articles to EPUB, downloads PDFs directly
3. Uploads to reMarkable via rmapi

### Cleanup logic
On each cycle, any previously-synced document that is no longer in the configured locations (archived, seen, deleted, moved) is automatically removed from reMarkable.

### Economist sync
When enabled, checks [evanbio/The_Economist](https://github.com/evanbio/The_Economist) for the latest weekly edition (published Sundays ~9 AM CST). Saves the PDF to your Readwise Reader library with title "The Economist: [Date]". The normal sync loop then handles uploading it to reMarkable.

### Highlight sync (reMarkable → Readwise)
When enabled, downloads annotated documents from reMarkable cloud via `rmapi get`, extracts highlighted text using [rmscene](https://github.com/ricklupton/rmscene) (for EPUBs) and [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (for PDFs), then pushes to Readwise via the [v2 Highlights API](https://readwise.io/api_deets).

## Troubleshooting

**Check logs:**
```bash
docker logs readwise-remarkable
```

**Re-authenticate rmapi** (via CLI if web UI isn't working):
```bash
docker exec -it readwise-remarkable rmapi ls
# Enter the device code when prompted, then:
docker exec readwise-remarkable cp /root/.config/rmapi/rmapi.conf /data/rmapi.conf
```

**Run sync manually:**
```bash
docker exec readwise-remarkable python sync.py
```
