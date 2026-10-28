"""Acoustic fingerprints (Chromaprint via ``fpcalc``) to spot the same recording
in different files, formats or bitrates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from ..tools import find_tool, run

FRAME_SECONDS = 0.1238  # duration covered by one Chromaprint sub-fingerprint
_POPCOUNT16 = np.array([bin(i).count("1") for i in range(1 << 16)], dtype=np.uint8)


def available() -> bool:
    return find_tool("fpcalc") is not None


def raw_fingerprint(path: Path, length: int = 120) -> Optional[tuple[float, list[int]]]:
    """Return ``(duration, [32-bit ints])`` for the first ``length`` seconds."""
    exe = find_tool("fpcalc")
    if not exe:
        return None
    try:
        res = run([exe, "-raw", "-json", "-length", str(length), str(path)])
        data = json.loads(res.stdout or b"{}")
        return float(data["duration"]), [int(x) & 0xFFFFFFFF for x in data["fingerprint"]]
    except (OSError, ValueError, KeyError):
        return None


def compressed_fingerprint(path: Path) -> Optional[tuple[float, str]]:
    """The compact fingerprint string expected by the AcoustID web service."""
    exe = find_tool("fpcalc")
    if not exe:
        return None
    try:
        data = json.loads(run([exe, "-json", str(path)]).stdout or b"{}")
        return float(data["duration"]), str(data["fingerprint"])
    except (OSError, ValueError, KeyError):
        return None


def similarity(a: list[int], b: list[int], max_offset: int = 40) -> float:
    """Fraction of matching bits (0..1) at the best alignment of ``a`` and ``b``.

    Unrelated audio scores about 0.5; the same recording, even re-encoded at a
    low bitrate, usually scores above 0.85. Offsets up to ~5 s are tried so
    files with a little extra silence at the start still match.
    """
    if not a or not b:
        return 0.0
    x_all = np.asarray(a, dtype=np.uint32)
    y_all = np.asarray(b, dtype=np.uint32)
    best = 0.0
    for offset in range(-max_offset, max_offset + 1):
        if offset >= 0:
            x, y = x_all[offset:], y_all
        else:
            x, y = x_all, y_all[-offset:]
        n = min(len(x), len(y))
        if n < 50:  # need ~6 s of overlap to be meaningful
            continue
        errors = int(_POPCOUNT16[(x[:n] ^ y[:n]).view(np.uint16)].sum())
        best = max(best, 1.0 - errors / (32.0 * n))
    return best


def coarse_set(fp: list[int]) -> frozenset:
    """Top 20 bits of each sub-fingerprint; re-encodes of a song share many."""
    return frozenset(x >> 12 for x in fp)


def may_match(a: frozenset, b: frozenset, min_overlap: float = 0.1) -> bool:
    """Cheap pre-check before ``similarity``: different songs share ~2%."""
    if not a or not b:
        return False
    return len(a & b) >= min_overlap * min(len(a), len(b))
