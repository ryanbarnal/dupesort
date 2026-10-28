"""AI photo upscaling with Real-ESRGAN (ncnn-vulkan build, runs on most GPUs).

The upscaler is ~50 MB, so it is downloaded on first use (after the user
agrees) into the app-data folder instead of being bundled with every install.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
from platformdirs import user_data_dir

from .. import APP_NAME, web
from ..tools import run
from .ffmpeg import ConversionError

RELEASE = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
ASSETS = {"darwin": "realesrgan-ncnn-vulkan-20220424-macos.zip",
          "win32": "realesrgan-ncnn-vulkan-20220424-windows.zip",
          "linux": "realesrgan-ncnn-vulkan-20220424-ubuntu.zip"}
SIZES_MB = {"darwin": 52, "win32": 45, "linux": 47}
MODEL = "realesrgan-x4plus"


def install_dir() -> Path:
    base = os.environ.get("DUPESORT_DATA", user_data_dir(APP_NAME, False))
    return Path(base) / "tools" / "realesrgan"


def _asset() -> Optional[str]:
    return ASSETS.get("linux" if sys.platform.startswith("linux") else sys.platform)


def download_size_mb() -> int:
    return SIZES_MB.get("linux" if sys.platform.startswith("linux") else sys.platform, 50)


def executable() -> Optional[Path]:
    name = "realesrgan-ncnn-vulkan" + (".exe" if os.name == "nt" else "")
    found = list(install_dir().rglob(name)) if install_dir().is_dir() else []
    return found[0] if found else None


def installed() -> bool:
    exe = executable()
    return bool(exe and (exe.parent / "models").is_dir())


def install(progress: Optional[Callable[[int, int], None]] = None) -> None:
    asset = _asset()
    if not asset:
        raise ConversionError("AI upscaling isn't available for this operating system.")
    r = web._session.get(RELEASE + asset, stream=True, timeout=60)
    if not r.ok:
        raise ConversionError(f"Download failed (HTTP {r.status_code}).")
    total = int(r.headers.get("content-length") or 0)
    target = install_dir()
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / asset
        done = 0
        with open(zpath, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        with zipfile.ZipFile(zpath) as z:
            for member in z.namelist():  # refuse paths escaping the folder
                if member.startswith("/") or ".." in Path(member).parts:
                    raise ConversionError("Unexpected file in download; aborted.")
            z.extractall(target)
    exe = executable()
    if not exe:
        raise ConversionError("Downloaded upscaler is missing its program file.")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ai_upscale(img: Image.Image, scale: int) -> Image.Image:
    """Upscale ``img`` 2x or 4x. The model is 4x; 2x is 4x then halved (sharper
    than a plain 2x resize)."""
    exe = executable()
    if not installed() or exe is None:
        raise ConversionError("The AI upscaler isn't installed yet.")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.png", Path(tmp) / "out.png"
        alpha = img.getchannel("A") if img.mode in ("RGBA", "LA") else None
        img.convert("RGB").save(src)
        res = run([str(exe), "-i", str(src), "-o", str(dst), "-n", MODEL, "-s", "4",
                   "-m", str(exe.parent / "models")], timeout=1800)
        if res.returncode != 0 or not dst.exists():
            msg = (res.stderr or b"").decode("utf-8", "ignore").strip().splitlines()
            raise ConversionError("AI upscaling failed" + (f": {msg[-1]}" if msg else
                                  " (no compatible graphics driver?)"))
        with Image.open(dst) as out:
            out.load()
            big = out.convert("RGB")
    if scale == 2:
        big = big.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    if alpha is not None:
        big.putalpha(alpha.resize(big.size, Image.LANCZOS))
    return big
