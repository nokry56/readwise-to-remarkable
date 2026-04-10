#!/usr/bin/env python3
"""Web UI for readwise-to-remarkable container settings and rmapi auth.

Zero-dependency — uses only Python stdlib (http.server, json, subprocess).
Runs as a background process alongside the sync loop.
"""

import json
import os
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

SETTINGS_FILE = Path("/data/settings.json")
CONFIG_FILE = Path("/app/config.cfg")
RMAPI_CONF = Path("/root/.config/rmapi/rmapi.conf")
RMAPI_CONF_PERSIST = Path("/data/rmapi.conf")

# Global state for rmapi auth flow
auth_state = {"active": False, "output": "", "success": False}


def load_settings() -> dict:
    """Load settings from persistent storage, falling back to env vars."""
    defaults = {
        "readwise_token": os.environ.get("READWISE_TOKEN", ""),
        "remarkable_folder": os.environ.get("REMARKABLE_FOLDER", "Readwise"),
        "sync_locations": os.environ.get("SYNC_LOCATIONS", "new,later,shortlist,feed"),
        "sync_tag": os.environ.get("SYNC_TAG", "*"),
        "sync_interval": os.environ.get("SYNC_INTERVAL", "1800"),
        "economist_enabled": os.environ.get("ECONOMIST_ENABLED", "false"),
        "highlight_sync_enabled": os.environ.get("HIGHLIGHT_SYNC_ENABLED", "false"),
    }
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open() as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_settings(settings: dict) -> None:
    """Save settings to persistent storage and regenerate config.cfg."""
    with SETTINGS_FILE.open("w") as f:
        json.dump(settings, f, indent=2)
    regenerate_config(settings)


def regenerate_config(settings: dict) -> None:
    """Write config.cfg from current settings."""
    cfg = f"""[readwise]
access_token = {settings['readwise_token']}

[remarkable]
rmapi_path = rmapi
folder = {settings['remarkable_folder']}

[sync]
locations = {settings['sync_locations']}
tag = {settings['sync_tag']}

[economist]
enabled = {settings['economist_enabled']}

[highlights]
enabled = {settings['highlight_sync_enabled']}
"""
    CONFIG_FILE.write_text(cfg)


def check_rmapi_auth() -> bool:
    """Check if rmapi is authenticated."""
    if not RMAPI_CONF.exists() and not RMAPI_CONF_PERSIST.exists():
        return False
    try:
        result = subprocess.run(
            ["rmapi", "ls", "/"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False


def start_rmapi_auth():
    """Start rmapi auth flow in a background thread."""
    auth_state["active"] = True
    auth_state["output"] = ""
    auth_state["success"] = False

    def run_auth():
        try:
            proc = subprocess.Popen(
                ["rmapi", "ls"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            output_lines = []
            for line in proc.stdout:
                output_lines.append(line)
                auth_state["output"] = "".join(output_lines)

            proc.wait(timeout=300)
            auth_state["success"] = proc.returncode == 0

            if auth_state["success"]:
                # Persist the auth token
                if RMAPI_CONF.exists():
                    subprocess.run(
                        ["cp", str(RMAPI_CONF), str(RMAPI_CONF_PERSIST)],
                        check=False,
                    )
        except Exception as e:
            auth_state["output"] += f"\nError: {e}"
        finally:
            auth_state["active"] = False

    threading.Thread(target=run_auth, daemon=True).start()


def render_page(settings: dict, message: str = "") -> str:
    """Render the settings page HTML."""
    rmapi_ok = check_rmapi_auth()
    rmapi_status = "Connected" if rmapi_ok else "Not authenticated"
    rmapi_color = "#22c55e" if rmapi_ok else "#ef4444"

    token_display = settings["readwise_token"]
    if len(token_display) > 8:
        token_display = token_display[:4] + "..." + token_display[-4:]

    msg_html = ""
    if message:
        msg_html = f'<div class="msg">{message}</div>'

    auth_html = ""
    if auth_state["active"]:
        output_escaped = auth_state["output"].replace("<", "&lt;").replace(">", "&gt;")
        auth_html = f"""
        <div class="auth-box">
            <h3>Authentication in progress...</h3>
            <pre>{output_escaped}</pre>
            <p>Follow the instructions above in your browser, then refresh this page.</p>
            <a href="/" class="btn">Refresh</a>
        </div>"""
    elif not rmapi_ok:
        auth_html = """
        <form method="POST" action="/auth">
            <button type="submit" class="btn btn-auth">Start reMarkable Authentication</button>
        </form>"""

    economist_checked = "checked" if settings["economist_enabled"].lower() == "true" else ""
    highlight_checked = "checked" if settings["highlight_sync_enabled"].lower() == "true" else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Readwise → reMarkable</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #0f172a; color: #e2e8f0; padding: 2rem; }}
.container {{ max-width: 640px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; color: #f8fafc; }}
h2 {{ font-size: 1.1rem; margin: 1.5rem 0 0.75rem; color: #94a3b8;
      text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500; }}
.status {{ display: inline-flex; align-items: center; gap: 0.5rem;
           padding: 0.25rem 0.75rem; border-radius: 1rem;
           background: #1e293b; font-size: 0.875rem; margin-bottom: 1rem; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: {rmapi_color}; }}
.msg {{ background: #164e63; padding: 0.75rem 1rem; border-radius: 0.5rem;
        margin-bottom: 1rem; font-size: 0.875rem; }}
.field {{ margin-bottom: 1rem; }}
label {{ display: block; font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.25rem;
         text-transform: uppercase; letter-spacing: 0.05em; }}
input[type="text"], input[type="password"], input[type="number"] {{
    width: 100%; padding: 0.625rem 0.75rem; background: #1e293b; border: 1px solid #334155;
    border-radius: 0.375rem; color: #e2e8f0; font-size: 0.9rem; }}
input:focus {{ outline: none; border-color: #3b82f6; }}
.check {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }}
.check input {{ width: 1.1rem; height: 1.1rem; accent-color: #3b82f6; }}
.check label {{ margin: 0; text-transform: none; font-size: 0.9rem; color: #e2e8f0; }}
.hint {{ font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }}
.btn {{ display: inline-block; padding: 0.625rem 1.5rem; background: #3b82f6;
        color: white; border: none; border-radius: 0.375rem; font-size: 0.9rem;
        cursor: pointer; text-decoration: none; }}
.btn:hover {{ background: #2563eb; }}
.btn-auth {{ background: #f59e0b; }}
.btn-auth:hover {{ background: #d97706; }}
.btn-sync {{ background: #22c55e; }}
.btn-sync:hover {{ background: #16a34a; }}
.actions {{ display: flex; gap: 0.75rem; margin-top: 1.5rem; }}
.auth-box {{ background: #1e293b; padding: 1rem; border-radius: 0.5rem;
             margin: 1rem 0; border: 1px solid #334155; }}
.auth-box pre {{ background: #0f172a; padding: 0.75rem; border-radius: 0.25rem;
                 font-size: 0.8rem; overflow-x: auto; margin: 0.5rem 0;
                 white-space: pre-wrap; word-break: break-all; }}
hr {{ border: none; border-top: 1px solid #1e293b; margin: 1.5rem 0; }}
.footer {{ font-size: 0.75rem; color: #475569; margin-top: 2rem; text-align: center; }}
</style>
</head>
<body>
<div class="container">
    <h1>Readwise → reMarkable</h1>
    <div class="status"><span class="dot"></span> reMarkable: {rmapi_status}</div>
    {auth_html}
    {msg_html}

    <form method="POST" action="/settings">
    <h2>Readwise</h2>
    <div class="field">
        <label>Access Token</label>
        <input type="password" name="readwise_token" value="{settings['readwise_token']}"
               placeholder="Get from readwise.io/access_token">
        <div class="hint">Current: {token_display}</div>
    </div>

    <h2>reMarkable</h2>
    <div class="field">
        <label>Upload Folder</label>
        <input type="text" name="remarkable_folder" value="{settings['remarkable_folder']}">
    </div>

    <h2>Sync</h2>
    <div class="field">
        <label>Locations</label>
        <input type="text" name="sync_locations" value="{settings['sync_locations']}">
        <div class="hint">Comma-separated: new, later, shortlist, feed</div>
    </div>
    <div class="field">
        <label>Tag Filter</label>
        <input type="text" name="sync_tag" value="{settings['sync_tag']}">
        <div class="hint">Use * for all documents</div>
    </div>
    <div class="field">
        <label>Sync Interval (seconds)</label>
        <input type="number" name="sync_interval" value="{settings['sync_interval']}" min="60">
        <div class="hint">1800 = 30 minutes</div>
    </div>

    <h2>Features</h2>
    <div class="check">
        <input type="checkbox" name="economist_enabled" id="econ" {economist_checked}>
        <label for="econ">Weekly Economist PDF (via Readwise)</label>
    </div>
    <div class="check">
        <input type="checkbox" name="highlight_sync_enabled" id="hl" {highlight_checked}>
        <label for="hl">Highlight sync (reMarkable → Readwise)</label>
    </div>

    <div class="actions">
        <button type="submit" class="btn">Save Settings</button>
        <a href="/sync" class="btn btn-sync">Run Sync Now</a>
    </div>
    </form>

    <hr>
    <div class="footer">readwise-to-remarkable &middot; Settings are saved to /data and persist across restarts</div>
</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/sync":
            # Trigger a manual sync in background
            threading.Thread(
                target=lambda: subprocess.run(
                    ["python", "-u", "/app/sync.py"],
                    capture_output=True,
                ),
                daemon=True,
            ).start()
            self.send_response(303)
            self.send_header("Location", "/?msg=Sync+triggered")
            self.end_headers()
            return

        settings = load_settings()
        msg = ""
        if "?msg=" in self.path:
            msg = self.path.split("?msg=")[1].replace("+", " ")

        html = render_page(settings, msg)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        params = parse_qs(body)

        if self.path == "/auth":
            start_rmapi_auth()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if self.path == "/settings":
            settings = load_settings()
            settings["readwise_token"] = params.get("readwise_token", [""])[0]
            settings["remarkable_folder"] = params.get("remarkable_folder", ["Readwise"])[0]
            settings["sync_locations"] = params.get("sync_locations", ["new,later,shortlist,feed"])[0]
            settings["sync_tag"] = params.get("sync_tag", ["*"])[0]
            settings["sync_interval"] = params.get("sync_interval", ["1800"])[0]
            settings["economist_enabled"] = "true" if "economist_enabled" in params else "false"
            settings["highlight_sync_enabled"] = "true" if "highlight_sync_enabled" in params else "false"

            save_settings(settings)

            self.send_response(303)
            self.send_header("Location", "/?msg=Settings+saved")
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress default access logs
        pass


def run(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Web UI running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    port = int(os.environ.get("WEBUI_PORT", "8080"))
    run(port)
