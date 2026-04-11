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
from collections import deque
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

SETTINGS_FILE = Path("/data/settings.json")
CONFIG_FILE = Path("/app/config.cfg")
RMAPI_CONF = Path("/root/.config/rmapi/rmapi.conf")
RMAPI_CONF_PERSIST = Path("/data/rmapi.conf")
SYNC_LOG_FILE = Path("/data/sync.log")

# Global state
auth_state = {"active": False, "output": "", "success": False}
sync_state = {"running": False, "last_run": "", "last_result": "", "log": deque(maxlen=50)}


def load_settings() -> dict:
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
    with SETTINGS_FILE.open("w") as f:
        json.dump(settings, f, indent=2)
    regenerate_config(settings)


def regenerate_config(settings: dict) -> None:
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

            if auth_state["success"] and RMAPI_CONF.exists():
                subprocess.run(["cp", str(RMAPI_CONF), str(RMAPI_CONF_PERSIST)], check=False)
        except Exception as e:
            auth_state["output"] += f"\nError: {e}"
        finally:
            auth_state["active"] = False

    threading.Thread(target=run_auth, daemon=True).start()


def run_manual_sync():
    sync_state["running"] = True
    sync_state["log"].clear()

    def do_sync():
        started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        sync_state["last_run"] = started
        sync_state["log"].append(f"--- Sync started at {started} ---")

        try:
            proc = subprocess.Popen(
                ["python", "-u", "/app/sync.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                sync_state["log"].append(line.rstrip())
            proc.wait(timeout=600)

            if proc.returncode == 0:
                sync_state["last_result"] = "success"
                sync_state["log"].append("--- Sync completed successfully ---")
            else:
                sync_state["last_result"] = "failed"
                sync_state["log"].append(f"--- Sync failed (exit code {proc.returncode}) ---")
        except Exception as e:
            sync_state["last_result"] = "error"
            sync_state["log"].append(f"--- Sync error: {e} ---")
        finally:
            sync_state["running"] = False

    threading.Thread(target=do_sync, daemon=True).start()


def get_tracker_stats() -> dict:
    tracker_file = Path("/app/exported_documents.json")
    if not tracker_file.exists():
        tracker_file = Path("/data/exported_documents.json")
    if not tracker_file.exists():
        return {"exported": 0, "highlights": 0}
    try:
        with tracker_file.open() as f:
            data = json.load(f)
        exported = len(data.get("exported", {}))
        highlights = sum(
            len(v.get("texts", [])) for v in data.get("highlights", {}).values()
        )
        return {"exported": exported, "highlights": highlights}
    except Exception:
        return {"exported": 0, "highlights": 0}


def render_page(settings: dict, message: str = "") -> str:
    rmapi_ok = check_rmapi_auth()
    rmapi_status = "Connected" if rmapi_ok else "Not authenticated"
    rmapi_color = "#22c55e" if rmapi_ok else "#ef4444"
    rmapi_icon = "&#10003;" if rmapi_ok else "&#10007;"

    token_val = settings["readwise_token"]
    token_display = ""
    if token_val and len(token_val) > 8:
        token_display = token_val[:4] + "..." + token_val[-4:]
    elif token_val:
        token_display = "***"

    stats = get_tracker_stats()

    msg_html = ""
    if message:
        msg_html = f'<div class="msg">{message}</div>'

    # rmapi auth section — always visible
    auth_html = ""
    if auth_state["active"]:
        output_escaped = auth_state["output"].replace("<", "&lt;").replace(">", "&gt;")
        auth_html = f"""
        <div class="auth-box">
            <h3>Authentication in progress...</h3>
            <pre>{output_escaped}</pre>
            <p>Follow the instructions above in your browser, then refresh this page.</p>
            <a href="/" class="btn" style="margin-top:0.5rem">Refresh</a>
        </div>"""
    else:
        auth_label = "Re-authenticate reMarkable" if rmapi_ok else "Authenticate reMarkable"
        auth_html = f"""
        <form method="POST" action="/auth" style="margin-top:0.5rem">
            <button type="submit" class="btn btn-auth">{auth_label}</button>
        </form>"""

    # Sync status section
    sync_running_class = "pulse" if sync_state["running"] else ""
    if sync_state["running"]:
        sync_status_text = "Running..."
        sync_status_color = "#3b82f6"
    elif sync_state["last_result"] == "success":
        sync_status_text = f"Last sync: {sync_state['last_run']}"
        sync_status_color = "#22c55e"
    elif sync_state["last_result"] == "failed":
        sync_status_text = f"Failed at {sync_state['last_run']}"
        sync_status_color = "#ef4444"
    else:
        sync_status_text = "No manual sync run yet"
        sync_status_color = "#64748b"

    sync_log_html = ""
    if sync_state["log"]:
        log_lines = "\n".join(sync_state["log"])
        log_escaped = log_lines.replace("<", "&lt;").replace(">", "&gt;")
        sync_log_html = f'<pre class="log-box">{log_escaped}</pre>'

    economist_checked = "checked" if settings["economist_enabled"].lower() == "true" else ""
    highlight_checked = "checked" if settings["highlight_sync_enabled"].lower() == "true" else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Readwise → reMarkable</title>
{"<meta http-equiv='refresh' content='3'>" if sync_state["running"] or auth_state["active"] else ""}
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #0f172a; color: #e2e8f0; padding: 1.5rem; }}
.container {{ max-width: 640px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin-bottom: 1rem; color: #f8fafc; }}
h2 {{ font-size: 1rem; margin: 1.25rem 0 0.6rem; color: #94a3b8;
      text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500; }}

.status-bar {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }}
.status-pill {{ display: inline-flex; align-items: center; gap: 0.4rem;
               padding: 0.3rem 0.75rem; border-radius: 1rem;
               background: #1e293b; font-size: 0.8rem; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.stat {{ font-variant-numeric: tabular-nums; }}

.msg {{ background: #164e63; padding: 0.6rem 0.875rem; border-radius: 0.5rem;
        margin-bottom: 1rem; font-size: 0.85rem; }}
.card {{ background: #1e293b; border-radius: 0.5rem; padding: 1rem;
         margin-bottom: 1rem; border: 1px solid #334155; }}

.field {{ margin-bottom: 0.875rem; }}
label {{ display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.2rem;
         text-transform: uppercase; letter-spacing: 0.04em; }}
input[type="text"], input[type="password"], input[type="number"] {{
    width: 100%; padding: 0.5rem 0.625rem; background: #0f172a; border: 1px solid #334155;
    border-radius: 0.375rem; color: #e2e8f0; font-size: 0.875rem; }}
input:focus {{ outline: none; border-color: #3b82f6; }}
.check {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.6rem; }}
.check input {{ width: 1rem; height: 1rem; accent-color: #3b82f6; }}
.check label {{ margin: 0; text-transform: none; font-size: 0.875rem; color: #e2e8f0; }}
.hint {{ font-size: 0.7rem; color: #64748b; margin-top: 0.15rem; }}

.btn {{ display: inline-block; padding: 0.5rem 1.25rem; background: #3b82f6;
        color: white; border: none; border-radius: 0.375rem; font-size: 0.85rem;
        cursor: pointer; text-decoration: none; }}
.btn:hover {{ background: #2563eb; }}
.btn-auth {{ background: #f59e0b; color: #0f172a; font-weight: 500; }}
.btn-auth:hover {{ background: #d97706; }}
.btn-sync {{ background: #22c55e; }}
.btn-sync:hover {{ background: #16a34a; }}
.btn-sm {{ padding: 0.35rem 0.75rem; font-size: 0.8rem; }}
.actions {{ display: flex; gap: 0.6rem; margin-top: 1.25rem; }}

.auth-box {{ background: #1e293b; padding: 0.875rem; border-radius: 0.5rem;
             margin: 0.75rem 0; border: 1px solid #334155; }}
.auth-box pre {{ background: #0f172a; padding: 0.625rem; border-radius: 0.25rem;
                 font-size: 0.75rem; overflow-x: auto; margin: 0.4rem 0;
                 white-space: pre-wrap; word-break: break-all; }}
.log-box {{ background: #0f172a; padding: 0.625rem; border-radius: 0.25rem;
            font-size: 0.7rem; max-height: 200px; overflow-y: auto;
            margin-top: 0.5rem; white-space: pre-wrap; word-break: break-word;
            color: #94a3b8; line-height: 1.4; }}

hr {{ border: none; border-top: 1px solid #1e293b; margin: 1.25rem 0; }}
.footer {{ font-size: 0.7rem; color: #475569; margin-top: 1.5rem; text-align: center; }}

@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
.pulse {{ animation: pulse 1.5s infinite; }}
</style>
</head>
<body>
<div class="container">
    <h1>Readwise → reMarkable</h1>

    <div class="status-bar">
        <div class="status-pill"><span class="dot" style="background:{rmapi_color}"></span> reMarkable: {rmapi_status}</div>
        <div class="status-pill"><span class="stat">{stats['exported']}</span> docs synced</div>
        <div class="status-pill"><span class="stat">{stats['highlights']}</span> highlights</div>
    </div>

    {msg_html}

    <div class="card">
        <h2 style="margin-top:0">reMarkable Cloud</h2>
        <div style="font-size:0.85rem; margin-bottom:0.5rem">
            Status: <span style="color:{rmapi_color}">{rmapi_icon} {rmapi_status}</span>
        </div>
        {auth_html}
    </div>

    <form method="POST" action="/settings">
    <div class="card">
        <h2 style="margin-top:0">Readwise</h2>
        <div class="field">
            <label>Access Token</label>
            <input type="password" name="readwise_token" value="{settings['readwise_token']}"
                   placeholder="Get from readwise.io/access_token">
            <div class="hint">Current: {token_display or 'not set'} &middot;
                <a href="https://readwise.io/access_token" target="_blank" style="color:#3b82f6">Get your token</a></div>
        </div>
    </div>

    <div class="card">
        <h2 style="margin-top:0">Sync Settings</h2>
        <div class="field">
            <label>Upload Folder</label>
            <input type="text" name="remarkable_folder" value="{settings['remarkable_folder']}">
        </div>
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
    </div>

    <div class="card">
        <h2 style="margin-top:0">Features</h2>
        <div class="check">
            <input type="checkbox" name="economist_enabled" id="econ" {economist_checked}>
            <label for="econ">Weekly Economist PDF (via Readwise)</label>
        </div>
        <div class="check">
            <input type="checkbox" name="highlight_sync_enabled" id="hl" {highlight_checked}>
            <label for="hl">Highlight sync (reMarkable → Readwise)</label>
        </div>
    </div>

    <div class="actions">
        <button type="submit" class="btn">Save Settings</button>
        <a href="/sync" class="btn btn-sync {"" if not sync_state["running"] else "pulse"}">
            {"Running..." if sync_state["running"] else "Run Sync Now"}</a>
    </div>
    </form>

    <div class="card" style="margin-top:1rem">
        <h2 style="margin-top:0">Sync Log</h2>
        <div style="font-size:0.8rem; color:{sync_status_color}" class="{sync_running_class}">
            {sync_status_text}
        </div>
        {sync_log_html}
    </div>

    <hr>
    <div class="footer">readwise-to-remarkable &middot; Settings saved to /data &middot; <a href="/" style="color:#64748b">Refresh</a></div>
</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/sync":
            if not sync_state["running"]:
                run_manual_sync()
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
        pass


def run(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Web UI running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    port = int(os.environ.get("WEBUI_PORT", "9080"))
    run(port)
