"""File operations that are always recorded so a whole session can be undone."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from platformdirs import user_data_dir

from .. import APP_NAME
from .longpath import exists, is_dir, lp
from .scanner import DUPLICATES_DIR, FileEntry

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def history_dir() -> Path:
    d = Path(os.environ.get("DUPESORT_DATA", user_data_dir(APP_NAME, False))) / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_filename(name: str, max_len: int = 180) -> str:
    """Make ``name`` valid on Windows, macOS and Linux."""
    name = _INVALID.sub("_", name).strip().rstrip(". ")
    name = re.sub(r"\s+", " ", name)
    stem, ext = os.path.splitext(name)
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    if len(stem) + len(ext) > max_len:
        stem = stem[: max_len - len(ext)].rstrip()
    return (stem + ext) or "_"


def unique_path(path: Path) -> Path:
    if not exists(path):
        return path
    stem, ext = path.stem, path.suffix
    n = 1
    while True:
        candidate = path.with_name(f"{stem} ({n}){ext}")
        if not exists(candidate):
            return candidate
        n += 1


@dataclass
class Session:
    """A batch of operations (one click of an action button)."""

    title: str
    ops: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    undone: bool = False
    file: Optional[Path] = None

    # -- recording ---------------------------------------------------------
    def _save(self) -> None:
        if self.file is None:
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.created))
            self.file = unique_path(history_dir() / f"{stamp}.json")
        data = {"title": self.title, "created": self.created,
                "undone": self.undone, "ops": self.ops}
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)

    def move(self, src: Path, dst: Path) -> Path:
        """Move ``src`` to ``dst`` (made unique), creating folders as needed."""
        src, dst = Path(src), Path(dst)
        # Compare the text, not the paths: on Windows "a.mp3" and "A.mp3" are equal paths,
        # which would skip a rename that only changes capital letters.
        if str(src) == str(dst):
            return dst
        # On case-insensitive filesystems "song.mp3" -> "Song.mp3" is the same file.
        # lp(): Windows paths of any length (moving into _Duplicates makes them longer).
        case_only = exists(dst) and os.path.samefile(lp(src), lp(dst))
        if not case_only:
            dst = unique_path(dst)
        os.makedirs(lp(dst.parent), exist_ok=True)
        if src.parent == dst.parent and src.name.lower() == dst.name.lower():
            # Case-only rename on a case-insensitive filesystem needs two steps.
            tmp = unique_path(src.with_name(src.name + ".dupesort-tmp"))
            os.rename(lp(src), lp(tmp))
            os.rename(lp(tmp), lp(dst))
        else:
            shutil.move(lp(src), lp(dst))
        self.ops.append({"op": "move", "src": str(src), "dst": str(dst)})
        self._save()
        return dst

    def rename(self, src: Path, new_name: str) -> Path:
        src = Path(src)
        new_name = safe_filename(new_name)
        if new_name == src.name:
            return src
        target = src.with_name(new_name)
        if target.exists() and target.name.lower() != src.name.lower():
            target = unique_path(target)
        return self.move(src, target)

    def record_tags(self, path: Path, before: dict, after: dict) -> None:
        self.ops.append({"op": "tags", "path": str(path), "before": before, "after": after})
        self._save()

    def move_duplicate(self, entry: FileEntry) -> Path:
        """Relocate a duplicate into ``<scan root>/_Duplicates/<original sub-path>``."""
        return self.move(entry.path, entry.root / DUPLICATES_DIR / entry.relative)

    # -- undo --------------------------------------------------------------
    def undo(self) -> list[str]:
        """Reverse every operation, newest first. Returns a list of problems."""
        problems = []
        for op in reversed(self.ops):
            try:
                if op["op"] == "move":
                    src, dst = Path(op["src"]), Path(op["dst"])
                    if not exists(dst):
                        problems.append(f"Missing, cannot restore: {dst}")
                    elif exists(src) and src.name.lower() != dst.name.lower():
                        problems.append(f"Original location is occupied: {src}")
                    else:
                        os.makedirs(lp(src.parent), exist_ok=True)
                        if src.parent == dst.parent and src.name.lower() == dst.name.lower():
                            tmp = unique_path(dst.with_name(dst.name + ".dupesort-tmp"))
                            os.rename(lp(dst), lp(tmp))
                            os.rename(lp(tmp), lp(src))
                        else:
                            shutil.move(lp(dst), lp(src))
                        _remove_empty_dirs(dst.parent)
                elif op["op"] == "tags":
                    from ..music.tags import write_tags

                    write_tags(Path(op["path"]), op["before"], clear_missing=True)
            except Exception as exc:  # keep undoing the rest
                problems.append(f"{op}: {exc}")
        self.undone = True
        self._save()
        return problems


def _remove_empty_dirs(folder: Path) -> None:
    """Remove now-empty folders up to (and including) the ``_Duplicates`` root."""
    folder = Path(folder)
    parts = folder.parts
    if DUPLICATES_DIR not in parts:
        return
    stop = Path(*parts[: parts.index(DUPLICATES_DIR)])
    while folder != stop and is_dir(folder):
        try:
            os.rmdir(lp(folder))
        except OSError:
            return
        folder = folder.parent


def load_sessions() -> list[Session]:
    out = []
    for f in sorted(history_dir().glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append(Session(data["title"], data["ops"], data["created"],
                           data.get("undone", False), f))
    return out
