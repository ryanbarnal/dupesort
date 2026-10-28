"""Shared HTTP session with polite per-host rate limiting and simple retries."""

from __future__ import annotations

import threading
import time
from typing import Optional
from urllib.parse import urlparse

import requests

from . import APP_NAME, __version__

USER_AGENT = f"{APP_NAME}/{__version__} ( https://github.com/dupesort/dupesort )"

# Minimum seconds between requests per host (MusicBrainz asks for 1/s).
_INTERVALS = {"musicbrainz.org": 1.1, "api.acoustid.org": 0.34}
_last: dict[str, float] = {}
_lock = threading.Lock()
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def _wait(host: str) -> None:
    gap = _INTERVALS.get(host, 0)
    if not gap:
        return
    with _lock:
        delay = _last.get(host, 0) + gap - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _last[host] = time.monotonic()


def get(url: str, params: Optional[dict] = None, timeout: float = 20,
        retries: int = 2, headers: Optional[dict] = None) -> Optional[requests.Response]:
    """GET returning the response, or None on network failure / 404."""
    host = urlparse(url).hostname or ""
    for attempt in range(retries + 1):
        _wait(host)
        try:
            r = _session.get(url, params=params, timeout=timeout, headers=headers)
        except requests.RequestException:
            if attempt == retries:
                return None
            time.sleep(1 + attempt)
            continue
        if r.status_code in (429, 503) and attempt < retries:
            time.sleep(2 + 2 * attempt)
            continue
        return r if r.ok else None
    return None


def get_json(url: str, params: Optional[dict] = None, **kw):
    r = get(url, params, **kw)
    if r is None:
        return None
    try:
        return r.json()
    except ValueError:
        return None
