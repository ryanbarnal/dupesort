"""Photos: exact and visually-similar duplicates, EXIF dates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import imagehash
from PIL import Image, ImageOps

from .core.duplicates import DuplicateGroup, merge_groups
from .core.hashing import find_exact_duplicates
from .core.scanner import FileEntry
from .core.similar import group_similar
from .settings import Settings
from .core.longpath import lp

try:  # iPhone HEIC photos, if the optional plugin is installed
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

Image.MAX_IMAGE_PIXELS = 400_000_000
EXIF_IFD, DATE_TAKEN, DATE_DIGITIZED, DATE_TIME = 0x8769, 36867, 36868, 306


def _parse_exif_date(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:19].replace("-", ":"), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def load_image_info(f: FileEntry) -> None:
    """Fill ``f.info`` with width, height, date taken and a 64-bit perceptual hash."""
    with Image.open(lp(f.path)) as img:
        f.info["width"], f.info["height"] = img.size
        exif = img.getexif()
        sub = exif.get_ifd(EXIF_IFD) if exif else {}
        f.info["date"] = (_parse_exif_date(sub.get(DATE_TAKEN)) or
                          _parse_exif_date(sub.get(DATE_DIGITIZED)) or
                          _parse_exif_date(exif.get(DATE_TIME) if exif else None))
        f.info["has_exif"] = bool(exif)
        img.draft("RGB", (512, 512))  # fast JPEG decode at reduced size
        img = ImageOps.exif_transpose(img)
        f.info["phash"] = int(str(imagehash.phash(img.convert("L"))), 16)


def quality(f: FileEntry) -> tuple:
    i = f.info
    return (i.get("width", 0) * i.get("height", 0), i.get("has_exif", False))


def find_duplicates(files: list[FileEntry], settings: Settings,
                    progress: Optional[Callable[[int, int, str], None]] = None,
                    cancelled: Callable[[], bool] = lambda: False) -> list[DuplicateGroup]:
    hashed = []
    for n, f in enumerate(files, 1):
        if cancelled():
            return []
        try:
            load_image_info(f)
            hashed.append((f.info["phash"], f))
        except Exception:
            f.info.setdefault("error", "Unreadable image")
        if progress and n % 10 == 0:
            progress(n, len(files), f"Analysing: {f.path.name}")
    found = [("Identical file", find_exact_duplicates(files, cancelled=cancelled))]
    if settings.photo_threshold > 0:
        found.append(("Similar image", group_similar(hashed, settings.photo_threshold)))
    return merge_groups(found)


def thumbnail(path: Path, size: int = 320):
    """A PIL thumbnail (RGB) for previews, or None."""
    try:
        with Image.open(lp(path)) as img:
            img.draft("RGB", (size * 2, size * 2))
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((size, size))
            return img
    except Exception:
        return None
