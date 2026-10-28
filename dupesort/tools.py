"""Locate optional external helpers (fpcalc, ffmpeg, ffprobe).

They are looked up next to the frozen executable first (so a packaged build
can bundle them), then in a ``bin`` folder beside the package, then on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=None)
def find_tool(name: str) -> Optional[str]:
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / exe)
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "bin" / exe)
    candidates.append(Path(__file__).resolve().parent.parent / "bin" / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which(name)


def run(args: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    """Run a helper without flashing a console window on Windows."""
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    return subprocess.run(args, capture_output=True, timeout=timeout, creationflags=flags)
