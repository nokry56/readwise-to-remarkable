# Readwise-to-reMarkable Docker

Syncs Readwise Reader articles to your reMarkable tablet. Tag documents with "remarkable" in Readwise Reader and they auto-upload as EPUBs via [rmapi](https://github.com/ddvk/rmapi).

Based on [donmerendolo/readwise-to-remarkable](https://github.com/donmerendolo/readwise-to-remarkable).

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

The "Readwise reMarkable" template will now appear when searching Apps.

### 2. Authenticate rmapi (one-time)

SSH into your Unraid server and run:

```bash
docker run -it --rm \
  -v /mnt/user/appdata/readwise-remarkable:/data \
  ghcr.io/nokry56/readwise-to-remarkable:latest rmapi
```

This opens rmapi interactively. It will display a URL and code. Open the URL in your browser, enter the code, and authorize. The auth token gets saved to `/data/.rmapi` and survives container restarts.

### 3. Install from Apps tab

1. Go to **Apps** tab, search "readwise"
2. Click **Install**
3. Fill in your **Readwise Token** (get it from https://readwise.io/access_token)
4. Adjust other settings if needed (defaults are fine)
5. Click **Apply**

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `READWISE_TOKEN` | *(required)* | Your Readwise access token |
| `REMARKABLE_FOLDER` | `Readwise` | Folder on reMarkable for uploads |
| `SYNC_LOCATIONS` | `new,later,shortlist` | Readwise locations to sync from |
| `SYNC_TAG` | `remarkable` | Tag to filter documents by |
| `SYNC_INTERVAL` | `1800` | Seconds between sync runs (30 min) |

## Usage

1. In Readwise Reader, tag any article/document with `remarkable`
2. The container syncs every 30 minutes (configurable)
3. Documents appear in the "Readwise" folder on your reMarkable

## Troubleshooting

**Check logs:**
```bash
docker logs readwise-remarkable
```

**Re-authenticate rmapi:**
```bash
docker exec -it readwise-remarkable rmapi
# Then persist the new token:
docker exec readwise-remarkable cp /root/.rmapi /data/.rmapi
```

**Run sync manually:**
```bash
docker exec readwise-remarkable python sync.py
```
