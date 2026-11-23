"""Check GitHub for a newer DupeSort release, download it and start the install.

Windows: the new Setup.exe is downloaded and runs silently, then DupeSort
restarts on the new version. macOS and Linux builds are not signed, so they
cannot replace themselves: the new .dmg / .tar.gz is downloaded and shown, and
the person drags it into place.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import RELEASES_API, RELEASES_PAGE, __version__

Progress = Optional[Callable[[int, int], None]]


@dataclass
class Release:
    version: str
    page: str
    notes: str = ""
    assets: dict[str, str] = field(default_factory=dict)  # file name -> download URL

    def installer(self) -> Optional[tuple[str, str]]:
        """(file name, URL) of the download for this computer, or None."""
        return pick_asset(self.assets)


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", (text or "").split("-")[0].split("+")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: Optional[str] = None) -> bool:
    return parse_version(candidate) > parse_version(current or __version__)


def pick_asset(assets: dict[str, str], system: Optional[str] = None,
               machine: Optional[str] = None) -> Optional[tuple[str, str]]:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    names = list(assets)
    if system == "Windows":
        wanted = [n for n in names if n.lower().endswith("setup.exe")]
    elif system == "Darwin":
        dmgs = [n for n in names if n.lower().endswith(".dmg")]
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
        wanted = [n for n in dmgs if arch in n.lower()] or dmgs
    else:
        wanted = [n for n in names if "linux" in n.lower() and n.lower().endswith(".tar.gz")]
    return (wanted[0], assets[wanted[0]]) if wanted else None


def from_github(data: dict) -> Optional[Release]:
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    if not tag:
        return None
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])
              if a.get("name") and a.get("browser_download_url")}
    return Release(tag.lstrip("vV"), data.get("html_url") or RELEASES_PAGE,
                   (data.get("body") or "").strip(), assets)


def latest_release(timeout: float = 15) -> Optional[Release]:
    """The newest published release, or None if GitHub can't be reached."""
    from . import web

    data = web.get_json(RELEASES_API, timeout=timeout, retries=1,
                        headers={"Accept": "application/vnd.github+json"})
    return from_github(data) if data else None


def check(timeout: float = 15) -> Optional[Release]:
    """The newest release if it is newer than this copy of DupeSort, else None."""
    rel = latest_release(timeout)
    return rel if rel and is_newer(rel.version) else None


def can_install_itself() -> bool:
    """Only the installed Windows app can update in place."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def download(url: str, name: str, progress: Progress = None,
             cancelled: Callable[[], bool] = lambda: False) -> Optional[Path]:
    """Download to the temp folder; returns the file, or None if cancelled."""
    from . import web

    folder = Path(tempfile.gettempdir()) / "DupeSort-update"
    folder.mkdir(parents=True, exist_ok=True)
    dest, part = folder / name, folder / (name + ".part")
    with web._session.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(part, "wb") as fh:
            for chunk in r.iter_content(chunk_size=256 * 1024):
                if cancelled():
                    fh.close()
                    part.unlink(missing_ok=True)
                    return None
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    os.replace(part, dest)
    return dest


def install(path: Path) -> bool:
    """Start installing ``path``. True means DupeSort should now quit (Windows)."""
    if sys.platform == "win32" and path.suffix.lower() == ".exe":
        # The installer closes nothing we still hold, replaces the app and starts it again.
        flags = ["/SILENT", "/SP-", "/NOCANCEL", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS"]
        subprocess.Popen([str(path), *flags], close_fds=True)
        return True
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # mounts the disk image in Finder
    else:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
    return False
