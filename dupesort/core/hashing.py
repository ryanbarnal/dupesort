"""Exact-duplicate detection: group by size, then partial hash, then full hash."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

from .scanner import FileEntry

from .longpath import lp

CHUNK = 1024 * 1024
PARTIAL_BYTES = 64 * 1024


def partial_hash(path: Path) -> str:
    """Hash the first and last 64 KiB - cheap and rules out most non-matches."""
    h = hashlib.blake2b(digest_size=16)
    with open(lp(path), "rb") as f:
        h.update(f.read(PARTIAL_BYTES))
        f.seek(0, 2)
        size = f.tell()
        if size > PARTIAL_BYTES * 2:
            f.seek(-PARTIAL_BYTES, 2)
            h.update(f.read(PARTIAL_BYTES))
    return h.hexdigest()


def full_hash(path: Path) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(lp(path), "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def find_exact_duplicates(
    files: list[FileEntry],
    progress: Optional[Callable[[int, int], None]] = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[list[FileEntry]]:
    """Return groups (2+ files) whose contents are byte-for-byte identical."""
    by_size: dict[int, list[FileEntry]] = defaultdict(list)
    for f in files:
        by_size[f.size].append(f)
    candidates = [g for g in by_size.values() if len(g) > 1]
    total = sum(len(g) for g in candidates)
    done = 0
    groups: list[list[FileEntry]] = []

    for same_size in candidates:
        by_partial: dict[str, list[FileEntry]] = defaultdict(list)
        for f in same_size:
            if cancelled():
                return groups
            try:
                by_partial[partial_hash(f.path)].append(f)
            except OSError:
                pass
            done += 1
            if progress:
                progress(done, total)
        for same_partial in by_partial.values():
            if len(same_partial) < 2:
                continue
            # Small files were fully covered by the partial hash already.
            if same_size[0].size <= PARTIAL_BYTES * 2:
                groups.append(same_partial)
                continue
            by_full: dict[str, list[FileEntry]] = defaultdict(list)
            for f in same_partial:
                if cancelled():
                    return groups
                try:
                    by_full[full_hash(f.path)].append(f)
                except OSError:
                    pass
            groups.extend(g for g in by_full.values() if len(g) > 1)
    return groups
