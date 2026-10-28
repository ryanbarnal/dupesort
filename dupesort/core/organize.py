"""Move files into date-based folders such as ``<root>/2024/07/``."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .history import Session
from .scanner import FileEntry


_NAME_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")


def date_from_name(name: str) -> Optional[datetime]:
    """Dates embedded by phones and apps: IMG_20230815_..., VID-20230815-WA0003, 2023-08-15 ..."""
    m = _NAME_DATE.search(name)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def date_folder(pattern: str, when: datetime) -> Path:
    return Path(pattern.format(year=when.year, month=when.month, day=when.day))


def file_date(f: FileEntry) -> datetime:
    return f.info.get("date") or date_from_name(f.path.name) or datetime.fromtimestamp(f.mtime)


def date_source(f: FileEntry) -> str:
    if f.info.get("date"):
        return "camera"
    return "file name" if date_from_name(f.path.name) else "file date"


def plan_date_moves(files: list[FileEntry], pattern: str,
                    dest_root: Optional[Path] = None) -> list[tuple[FileEntry, Path]]:
    """Return ``(file, target)`` for every file not already in its date folder.

    ``file.info["date"]`` (a datetime) is used when present, then a date in the
    file name, else the modification time. Targets live under ``dest_root`` or
    the file's scan root.
    """
    moves = []
    for f in files:
        when = file_date(f)
        base = Path(dest_root) if dest_root else f.root
        target = base / date_folder(pattern, when) / f.path.name
        if target.parent.resolve() != f.path.parent.resolve():
            moves.append((f, target))
    return moves


def apply_moves(moves: list[tuple[FileEntry, Path]], session: Session,
                progress: Optional[Callable[[int, int, str], None]] = None) -> list[str]:
    errors = []
    for n, (f, target) in enumerate(moves, 1):
        try:
            f.path = session.move(f.path, target)
        except OSError as exc:
            errors.append(f"{f.path}: {exc}")
        if progress:
            progress(n, len(moves), f.path.name)
    return errors
