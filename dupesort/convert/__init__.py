"""File converters: audio, images, video and PDF. Originals are never changed."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.history import unique_path


def output_path(src: Path, ext: str, out_dir: Optional[Path] = None, suffix: str = "") -> Path:
    """Where to write the converted copy of ``src`` - never over the original."""
    folder = Path(out_dir) if out_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{src.stem}{suffix}.{ext.lstrip('.')}"
    if target.resolve() == src.resolve():
        target = folder / f"{src.stem} (converted).{ext.lstrip('.')}"
    return unique_path(target)
