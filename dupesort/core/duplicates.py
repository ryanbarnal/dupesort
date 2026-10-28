"""Duplicate groups, merging results from several detectors, and keeper selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from .scanner import FileEntry

_COPY_NAME = re.compile(r"(\bcopy\b|\bkopie\b|\bcopie\b|\(\d+\)\s*$)", re.I)

KEEP_STRATEGIES = {
    "best": "Best quality",
    "oldest": "Oldest file",
    "newest": "Newest file",
    "shortest": "Shortest path",
}


@dataclass
class DuplicateGroup:
    files: list[FileEntry]
    reason: str  # e.g. "Identical content", "Same song", "Similar image"
    keep: set[int] = field(default_factory=lambda: {0})  # indexes of files to keep

    @property
    def duplicates(self) -> list[FileEntry]:
        return [f for i, f in enumerate(self.files) if i not in self.keep]

    @property
    def wasted_bytes(self) -> int:
        return sum(f.size for f in self.duplicates)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def merge_groups(
    labelled: Iterable[tuple[str, list[list[FileEntry]]]],
) -> list[DuplicateGroup]:
    """Merge overlapping groups from different detectors into one group each.

    ``labelled`` is a sequence of ``(reason, groups)``. A file that appears in
    an exact-hash group and a fingerprint group ends up in a single combined
    group; its reason lists every detector that matched.
    """
    uf = _UnionFind()
    entries: dict[str, FileEntry] = {}
    reasons: dict[str, list[str]] = {}
    for reason, groups in labelled:
        for group in groups:
            keys = [str(f.path) for f in group]
            for f, k in zip(group, keys):
                entries.setdefault(k, f)
                uf.union(keys[0], k)
            reasons.setdefault(keys[0], [])
            reasons[keys[0]].append(reason)

    clusters: dict[str, list[str]] = {}
    for k in entries:
        clusters.setdefault(uf.find(k), []).append(k)
    cluster_reasons: dict[str, list[str]] = {}
    for first, rs in reasons.items():
        bucket = cluster_reasons.setdefault(uf.find(first), [])
        bucket.extend(r for r in rs if r not in bucket)

    out = []
    for root, keys in clusters.items():
        if len(keys) < 2:
            continue
        files = sorted((entries[k] for k in keys), key=lambda f: str(f.path))
        out.append(DuplicateGroup(files, " + ".join(cluster_reasons.get(root, ["Duplicate"]))))
    out.sort(key=lambda g: -g.wasted_bytes)
    return out


def choose_keepers(
    groups: list[DuplicateGroup],
    strategy: str = "best",
    quality: Optional[Callable[[FileEntry], tuple]] = None,
    preferred_folder: Optional[Path] = None,
) -> None:
    """Set ``group.keep`` to the single best file of each group, in place.

    A file inside ``preferred_folder`` always wins. Otherwise ``strategy``
    decides; "best" uses the category's ``quality`` key (higher is better)
    with file size as the fallback.
    """
    pref = Path(preferred_folder).resolve() if preferred_folder else None

    def in_pref(f: FileEntry) -> bool:
        if pref is None:
            return False
        try:
            f.path.resolve().relative_to(pref)
            return True
        except ValueError:
            return False

    for g in groups:
        def key(i: int):
            f = g.files[i]
            if strategy == "oldest":
                base: tuple = (-f.mtime,)
            elif strategy == "newest":
                base = (f.mtime,)
            elif strategy == "shortest":
                base = (-len(str(f.path)),)
            else:
                base = (quality(f) if quality else ()) + (f.size,)
            # Ties: prefer the original over "x copy" / "x (1)", then the older file.
            return (in_pref(f),) + base + (not _COPY_NAME.search(f.path.stem), -f.mtime)

        g.keep = {max(range(len(g.files)), key=key)}
