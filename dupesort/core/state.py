"""Remember each page's work between runs: the scanned files, the duplicate groups (with
which copy is ticked to keep), the online tag lookups and the convert lists.

Saved as compressed JSON in the app's data folder. On loading, files that have been moved,
deleted or changed since are left out, so the results never point at stale files.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from platformdirs import user_data_dir

from .. import APP_NAME
from .duplicates import DuplicateGroup
from .scanner import FileEntry

VERSION = 1
# Large or rebuildable extras that aren't worth saving.
_SKIP_INFO = {"frames"}


def state_dir() -> Path:
    d = Path(os.environ.get("DUPESORT_DATA", user_data_dir(APP_NAME, False))) / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(name: str) -> Path:
    return state_dir() / f"{name}.json.gz"


# --- encoding ----------------------------------------------------------------------------------

def _plain(value: Any) -> Any:
    """Make ``value`` JSON-friendly (datetimes are tagged so they come back as datetimes)."""
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, bytes):
        return None
    return value


def _revive(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$dt"}:
            try:
                return datetime.fromisoformat(value["$dt"])
            except (TypeError, ValueError):
                return None
        return {k: _revive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_revive(v) for v in value]
    return value


def _entry_out(f: FileEntry) -> dict:
    info = {k: v for k, v in f.info.items() if k not in _SKIP_INFO}
    tags = info.get("tags")
    if isinstance(tags, dict) and tags.get("lyrics"):
        # Lyrics can be long; the preview only needs to know they're there.
        info["tags"] = {**tags, "lyrics": "(embedded)"}
    return {"path": str(f.path), "size": f.size, "mtime": f.mtime, "root": str(f.root),
            "info": _plain(info)}


def _entry_in(d: dict) -> FileEntry:
    return FileEntry(Path(d["path"]), int(d["size"]), float(d["mtime"]), Path(d["root"]),
                     _revive(d.get("info") or {}))


def _unchanged(f: FileEntry) -> bool:
    """Is the file still there, with the same size and modification time?"""
    try:
        st = f.path.stat()
    except OSError:
        return False
    return st.st_size == f.size and abs(st.st_mtime - f.mtime) < 2


def _proposal_out(p) -> dict:
    d = asdict(p)
    d["path"] = str(p.path)
    return _plain(d)


def _proposal_in(d: dict):
    from ..music.lookup import Match, Proposal

    d = _revive(d)
    matches = [Match(**m) for m in d.pop("matches", [])]
    return Proposal(path=Path(d.pop("path")), matches=matches, **d)


# --- pages -------------------------------------------------------------------------------------

def save_page(category: str, files: list[FileEntry], groups: list[DuplicateGroup],
              section: int = 0, proposals: Optional[list] = None,
              convert: Optional[dict] = None, interrupted: str = "") -> None:
    """Write one page's state (atomically, so a crash mid-write never leaves a broken file)."""
    index = {str(f.path): i for i, f in enumerate(files)}
    out_groups = []
    for g in groups:
        ids = []
        for f in g.files:
            key = str(f.path)
            if key not in index:  # a grouped file that isn't in the scan list
                index[key] = len(files)
                files = files + [f]
            ids.append(index[key])
        out_groups.append({"files": ids, "reason": g.reason, "keep": sorted(g.keep)})
    data = {
        "version": VERSION,
        "saved": time.time(),
        "section": section,
        "files": [_entry_out(f) for f in files],
        "groups": out_groups,
        "proposals": [_proposal_out(p) for p in proposals or []],
        "convert": _plain(convert or {}),
        "interrupted": interrupted,
    }
    target = _path(category)
    tmp = target.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, target)


def load_page(category: str) -> Optional[dict]:
    """The saved state of a page, with stale files left out; None if nothing usable."""
    try:
        with gzip.open(_path(category), "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, EOFError):
        return None
    if data.get("version") != VERSION:
        return None
    try:
        files = [_entry_in(d) for d in data.get("files", [])]
    except (KeyError, TypeError, ValueError):
        return None

    # Rebuild the groups from files that are still as they were.
    groups, dropped = [], 0
    checked: dict[int, bool] = {}
    for g in data.get("groups", []):
        keep_old = set(g.get("keep", []))
        kept_files, keep = [], set()
        for i in g.get("files", []):
            if not 0 <= i < len(files):
                continue
            if i not in checked:
                checked[i] = _unchanged(files[i])
            if checked[i]:
                if i in keep_old:
                    keep.add(len(kept_files))
                kept_files.append(files[i])
            else:
                dropped += 1
        if len(kept_files) < 2:
            continue
        groups.append(DuplicateGroup(kept_files, g.get("reason", "Duplicate"), keep or {0}))
    files = [f for i, f in enumerate(files) if checked.get(i, True)]

    proposals = []
    for d in data.get("proposals", []):
        try:
            p = _proposal_in(d)
        except (KeyError, TypeError, ValueError):
            continue
        if p.path.exists():
            proposals.append(p)

    return {
        "saved": data.get("saved", 0),
        "section": int(data.get("section", 0)),
        "files": files,
        "groups": groups,
        "proposals": proposals,
        "convert": data.get("convert") or {},
        "interrupted": data.get("interrupted", ""),
        "dropped": dropped,
    }


def clear_page(category: str) -> None:
    try:
        _path(category).unlink()
    except OSError:
        pass


# --- window ------------------------------------------------------------------------------------

def save_window(data: dict) -> None:
    target = state_dir() / "window.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, target)


def load_window() -> dict:
    try:
        return json.loads((state_dir() / "window.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
