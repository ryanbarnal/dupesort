"""File converters: audio, images, video and PDF. Originals are never changed."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import json
import os
import threading

from ..core.history import history_dir, unique_path

_LOCK = threading.Lock()
_MAX_PAIRS = 50_000


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _registry() -> Path:
    return history_dir().parent / "conversions.json"


def record_conversion(src: Path, dst: Path) -> None:
    """Remember that ``dst`` is a converted copy of ``src``, so a later scan that finds both
    keeps the converted copy and offers the original as the duplicate."""
    with _LOCK:
        pairs = conversions()
        pairs.append([_key(src), _key(dst)])
        try:
            tmp = _registry().with_suffix(".tmp")
            tmp.write_text(json.dumps(pairs[-_MAX_PAIRS:]), encoding="utf-8")
            os.replace(tmp, _registry())
        except OSError:
            pass


def conversions() -> list[list[str]]:
    """[original, converted] path pairs, oldest first."""
    try:
        data = json.loads(_registry().read_text(encoding="utf-8"))
        return [p for p in data if isinstance(p, list) and len(p) == 2]
    except (OSError, ValueError):
        return []


def output_path(src: Path, ext: str, out_dir: Optional[Path] = None, suffix: str = "") -> Path:
    """Where to write the converted copy of ``src`` - never over the original."""
    folder = Path(out_dir) if out_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{src.stem}{suffix}.{ext.lstrip('.')}"
    if target.resolve() == src.resolve():
        target = folder / f"{src.stem} (converted).{ext.lstrip('.')}"
    return unique_path(target)
