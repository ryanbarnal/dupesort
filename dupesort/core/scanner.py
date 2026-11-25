"""Walk folders and collect files belonging to a media category."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

DUPLICATES_DIR = "_Duplicates"
# Originals that a conversion replaced in place (see convert.audio); never scanned.
CONVERTED_DIR = "_Converted"

CATEGORY_EXTENSIONS = {
    "music": {
        ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wma",
        ".wav", ".aiff", ".aif", ".ape", ".wv", ".alac",
    },
    "photos": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp",
        ".heic", ".heif",
    },
    "videos": {
        ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".mpg", ".mpeg", ".3gp", ".ts", ".mts", ".m2ts",
    },
    "documents": {
        ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".xls",
        ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp", ".epub",
    },
}

# Folders that never contain user media and are expensive to walk.
SKIP_DIRS = {
    DUPLICATES_DIR, CONVERTED_DIR, ".git", ".svn", "node_modules", "__pycache__", ".Trash",
    "$RECYCLE.BIN", "System Volume Information", ".venv",
}


@dataclass
class FileEntry:
    path: Path
    size: int
    mtime: float
    root: Path  # the scan root this file was found under
    info: dict = field(default_factory=dict)  # category-specific extras

    @property
    def relative(self) -> Path:
        try:
            return self.path.relative_to(self.root)
        except ValueError:
            return Path(self.path.name)


def category_for(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    for cat, exts in CATEGORY_EXTENSIONS.items():
        if ext in exts:
            return cat
    return None


def scan(
    roots: Iterable[Path],
    category: str,
    min_size: int = 1,
    exclude: Iterable[str] = (),
    progress: Optional[Callable[[int, str], None]] = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[FileEntry]:
    """Return every file of ``category`` under ``roots``.

    Hidden files, ``_Duplicates`` folders and anything whose path contains one
    of the ``exclude`` substrings are skipped. Paths are de-duplicated so that
    overlapping roots do not report the same file twice.
    """
    exts = CATEGORY_EXTENSIONS[category]
    exclude = [e.lower() for e in exclude if e]
    seen: set[str] = set()
    found: list[FileEntry] = []

    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if cancelled():
                return found
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]
            for name in filenames:
                if name.startswith(".") or os.path.splitext(name)[1].lower() not in exts:
                    continue
                full = os.path.join(dirpath, name)
                if exclude and any(e in full.lower() for e in exclude):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                key = os.path.normcase(os.path.realpath(full))
                if key in seen or st.st_size < min_size:
                    continue
                seen.add(key)
                found.append(FileEntry(Path(full), st.st_size, st.st_mtime, root))
                if progress and len(found) % 200 == 0:
                    progress(len(found), full)
    if progress:
        progress(len(found), "")
    return found
