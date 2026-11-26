"""DupeSort Key Maker: the owner's app for making DupeSort license keys.

Double-click it: it opens a page in the default browser, served only to this computer, and
closes by itself a few minutes after the page is closed. The page (packaging/DupeSort Key
Maker.html) does the cryptography; this program keeps the files:

- the signing key file (locked with a password), by default next to this program,
- a ledger of every key made ("DupeSort keys ledger.csv", next to the key file),
- where the key file is ("settings.json" in the user's settings folder).

Only the Python standard library is used, so it builds into one portable file:

    pyinstaller --onefile --windowed --name "DupeSort Key Maker" \
        --add-data "packaging/DupeSort Key Maker.html:." packaging/keymaker.py

(.github/workflows/keymaker.yml builds it for Windows and macOS.)
"""

from __future__ import annotations

import csv
import hmac
import io
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

APP = "DupeSort Key Maker"
PAGE_NAME = "DupeSort Key Maker.html"
KEY_NAME = "dupesort-signing-key.txt"
LEDGER_NAME = "DupeSort keys ledger.csv"
IDLE_EXIT = 180  # seconds without the page before the program closes itself
LEDGER_FIELDS = ["date", "name", "key"]


# --- places ------------------------------------------------------------------------------------

def program_dir() -> Path:
    """The folder you see the program in: next to the .exe, or next to the .app on a Mac."""
    if getattr(sys, "frozen", False):
        d = Path(sys.executable).resolve().parent
        if sys.platform == "darwin" and d.name == "MacOS" and d.parent.name == "Contents":
            return d.parent.parent.parent
        return d
    # Run from source: the home folder, never inside the repository.
    return Path.home()


def page_file() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / PAGE_NAME


def config_dir() -> Path:
    if os.environ.get("DUPESORT_KEYMAKER_CONFIG"):
        return Path(os.environ["DUPESORT_KEYMAKER_CONFIG"])
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP


def clean_path(text: str) -> Path:
    """A path as people paste it: in quotes (Windows "Copy as path") or starting with ~."""
    t = (text or "").strip().strip('"').strip("'")
    return Path(os.path.expanduser(t))


# --- the app -----------------------------------------------------------------------------------

class KeyMaker:
    def __init__(self, start_dir: Optional[Path] = None) -> None:
        self.token = secrets.token_urlsafe(24)
        self.start_dir = start_dir or program_dir()
        self.last_seen = time.monotonic()
        self.lock = threading.Lock()

    # settings: where the key file is
    def _settings_path(self) -> Path:
        return config_dir() / "settings.json"

    def key_file(self) -> Optional[Path]:
        try:
            p = json.loads(self._settings_path().read_text(encoding="utf-8")).get("key_file")
            return Path(p) if p else None
        except (OSError, ValueError):
            default = self.start_dir / KEY_NAME
            return default if default.exists() else None

    def remember(self, path: Path) -> None:
        s = self._settings_path()
        s.parent.mkdir(parents=True, exist_ok=True)
        s.write_text(json.dumps({"key_file": str(path)}), encoding="utf-8")

    def ledger_path(self) -> Optional[Path]:
        k = self.key_file()
        return k.parent / LEDGER_NAME if k else None

    # actions (each returns a JSON-able dict, or raises ValueError with a message for the page)
    def state(self) -> dict:
        k = self.key_file()
        exists = bool(k and k.is_file())
        locked = False
        if exists:
            try:
                locked = k.read_text(encoding="utf-8").strip().startswith("DUPESORT-PRIVATE-KEY-")
            except OSError:
                exists = False
        return {"keyFile": str(k) if k else "", "exists": exists, "locked": locked,
                "newKeyFile": str(self.start_dir / KEY_NAME), "ledger": self.ledger()}

    def read_key(self, path: str = "") -> dict:
        p = clean_path(path) if path else self.key_file()
        if not p:
            raise ValueError("No signing key file has been chosen yet.")
        if p.is_dir():
            p = p / KEY_NAME
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            raise ValueError(f"Couldn't open {p}.") from None
        if len(text) > 4096:
            raise ValueError("That file is too big to be a signing key.")
        self.remember(p.resolve())
        return {"path": str(p.resolve()), "text": text}

    def save_key(self, text: str, path: str = "") -> dict:
        p = clean_path(path) if path else self.start_dir / KEY_NAME
        if p.is_dir():
            p = p / KEY_NAME
        if p.exists():
            raise ValueError(f"{p} already exists. Open it instead, or choose another place.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        try:
            p.chmod(0o600)
        except OSError:
            pass
        self.remember(p.resolve())
        return {"path": str(p.resolve())}

    def ledger(self) -> list[dict]:
        p = self.ledger_path()
        if not p or not p.exists():
            return []
        try:
            with open(p, newline="", encoding="utf-8-sig") as fh:
                return [{k: row.get(k, "") for k in LEDGER_FIELDS} for row in csv.DictReader(fh)]
        except (OSError, csv.Error):
            return []

    def add_to_ledger(self, row: dict) -> dict:
        p = self.ledger_path()
        if not p:
            raise ValueError("Open your signing key first.")
        new = not p.exists()
        with self.lock, open(p, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as fh:
            w = csv.DictWriter(fh, LEDGER_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: str(row.get(k, "")) for k in LEDGER_FIELDS})
        return {"ledger": self.ledger(), "path": str(p)}

    def reveal(self) -> dict:
        k = self.key_file()
        folder = k.parent if k else self.start_dir
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - opens Explorer on the folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return {}


def make_handler(app: KeyMaker):
    page = page_file().read_text(encoding="utf-8")
    actions = {
        "/api/state": lambda b: app.state(),
        "/api/key/read": lambda b: app.read_key(b.get("path", "")),
        "/api/key/save": lambda b: app.save_key(b["text"], b.get("path", "")),
        "/api/ledger/add": lambda b: app.add_to_ledger(b),
        "/api/reveal": lambda b: app.reveal(),
        "/api/ping": lambda b: {},
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def _local(self) -> bool:
            # Only pages from this program on this computer (guards against DNS rebinding).
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            app.last_seen = time.monotonic()
            if not self._local():
                return self._send(403, b"Forbidden", "text/plain")
            if self.path.split("?")[0] in ("/", "/index.html"):
                token = self.path.partition("t=")[2].split("&")[0]
                if not hmac.compare_digest(token, app.token):
                    return self._send(403, b"Open DupeSort Key Maker again to get a new page.",
                                      "text/plain; charset=utf-8")
                boot = f"<script>window.KEYMAKER = {json.dumps({'token': app.token})};</script>"
                html = page.replace("<script id=\"core\">", boot + "\n<script id=\"core\">", 1)
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            self._send(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            app.last_seen = time.monotonic()
            if not self._local() or not hmac.compare_digest(
                    self.headers.get("X-Token", ""), app.token):
                return self._send(403, b'{"error":"Forbidden"}', "application/json")
            fn = actions.get(self.path)
            if fn is None:
                return self._send(404, b'{"error":"Not found"}', "application/json")
            try:
                size = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
                body = json.loads(self.rfile.read(size) or b"{}")
                result, code = fn(body if isinstance(body, dict) else {}), 200
            except ValueError as exc:
                result, code = {"error": str(exc)}, 400
            except Exception as exc:  # keep the program running whatever happens
                result, code = {"error": f"{type(exc).__name__}: {exc}"}, 500
            self._send(code, json.dumps(result).encode(), "application/json")

    return Handler


def serve(app: KeyMaker, open_browser: bool = True) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.token}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if open_browser:
        webbrowser.open(url)
    return server, url


def main() -> None:
    open_browser = "--no-browser" not in sys.argv
    app = KeyMaker()
    server, url = serve(app, open_browser)
    if not open_browser:
        print(url, flush=True)
    # Close a few minutes after the page is gone (the page checks in every 30 seconds).
    while time.monotonic() - app.last_seen < IDLE_EXIT:
        time.sleep(5)
    server.shutdown()


if __name__ == "__main__":
    main()
