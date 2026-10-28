"""Run FFmpeg with live progress, cancellation and encoder fallbacks."""

from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from ..tools import find_tool, run


class ConversionError(Exception):
    pass


def require() -> str:
    exe = find_tool("ffmpeg")
    if not exe:
        raise ConversionError("FFmpeg is needed for audio and video conversion. "
                              "Install it (see Help → User Guide) and restart DupeSort.")
    return exe


@lru_cache(maxsize=1)
def encoders() -> frozenset:
    exe = find_tool("ffmpeg")
    if not exe:
        return frozenset()
    out = run([exe, "-hide_banner", "-encoders"], timeout=30).stdout.decode("utf-8", "ignore")
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


def pick_encoder(*candidates: str) -> str:
    """First candidate this FFmpeg build supports (the last one is the fallback)."""
    have = encoders()
    for c in candidates:
        if c in have:
            return c
    return candidates[-1]


def probe(path: Path) -> dict:
    exe = find_tool("ffprobe")
    if not exe:
        return {}
    try:
        out = run([exe, "-v", "quiet", "-print_format", "json", "-show_format",
                   "-show_streams", str(path)], timeout=60).stdout
        return json.loads(out or b"{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def duration_of(info: dict) -> float:
    try:
        return float(info.get("format", {}).get("duration") or 0)
    except ValueError:
        return 0.0


def convert(args: list[str], duration: float,
            progress: Optional[Callable[[float], None]] = None,
            cancelled: Callable[[], bool] = lambda: False) -> None:
    """Run ``ffmpeg <args>``; ``progress`` gets 0..1. Raises on failure/cancel."""
    exe = require()
    cmd = [exe, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats"] + args
    flags = 0x08000000 if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=flags)
    try:
        for raw in proc.stdout:
            if cancelled():
                proc.kill()
                raise ConversionError("Cancelled")
            line = raw.decode("utf-8", "ignore").strip()
            if line.startswith("out_time_us=") and duration > 0 and progress:
                try:
                    progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration))
                except ValueError:
                    pass
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        err = proc.stderr.read().decode("utf-8", "ignore").strip().splitlines()
        raise ConversionError(err[-1] if err else f"FFmpeg failed ({proc.returncode})")
    if progress:
        progress(1.0)


def remove_partial(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass
