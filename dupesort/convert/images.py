"""Convert photos to JPEG / PNG / WebP, upscale them, or shrink their file size."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter, ImageOps

from .. import photos  # noqa: F401  (registers the HEIC opener)
from . import output_path

FORMATS = {"Keep format": None, "JPEG": "jpg", "PNG": "png", "WebP": "webp"}
RESIZE_MODES = ("Keep size", "Scale by percent", "Fit within (pixels)",
                "Upscale 2× (simple)", "Upscale 4× (simple)",
                "Upscale 2× (AI)", "Upscale 4× (AI)")


@dataclass
class ImageOptions:
    fmt: str = "JPEG"
    resize: str = "Keep size"
    percent: int = 50
    max_side: int = 2048
    quality: int = 85  # JPEG / WebP
    png_reduce_colors: bool = False  # 256-colour palette: much smaller PNGs
    strip_metadata: bool = False  # drop camera, GPS location and other EXIF data
    out_dir: Optional[Path] = None


def _ext_for(src: Path, fmt: str) -> str:
    ext = FORMATS[fmt]
    if ext:
        return ext
    e = src.suffix.lower().lstrip(".")
    return {"jpeg": "jpg", "heic": "jpg", "heif": "jpg", "tif": "png", "tiff": "png",
            "bmp": "png", "gif": "png"}.get(e, e)


def _resize(img: Image.Image, opts: ImageOptions) -> Image.Image:
    w, h = img.size
    mode = opts.resize
    if mode == "Scale by percent":
        f = max(1, opts.percent) / 100
        return img.resize((max(1, round(w * f)), max(1, round(h * f))), Image.LANCZOS)
    if mode == "Fit within (pixels)":
        if max(w, h) <= opts.max_side:
            return img
        img = img.copy()
        img.thumbnail((opts.max_side, opts.max_side), Image.LANCZOS)
        return img
    if mode.startswith("Upscale") and "(simple)" in mode:
        factor = 4 if "4×" in mode else 2
        big = img.resize((w * factor, h * factor), Image.LANCZOS)
        # Mild sharpening recovers some of the crispness lost when enlarging.
        return big.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    return img


def convert_image(src: Path, opts: ImageOptions) -> Path:
    ext = _ext_for(src, opts.fmt)
    with Image.open(src) as im:
        exif = im.info.get("exif") if not opts.strip_metadata else None
        icc = im.info.get("icc_profile")
        img = ImageOps.exif_transpose(im)
        img.load()
    if exif:
        # The pixels are already rotated upright; reset the orientation tag.
        try:
            e = Image.Exif()
            e.load(exif)
            e[0x0112] = 1
            exif = e.tobytes()
        except Exception:
            exif = None

    if "(AI)" in opts.resize:
        from .upscale import ai_upscale

        img = ai_upscale(img, 4 if "4×" in opts.resize else 2)
    else:
        img = _resize(img, opts)

    if ext in ("jpg", "jpeg"):
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        save = {"format": "JPEG", "quality": opts.quality, "optimize": True,
                "progressive": True, "subsampling": 0 if opts.quality >= 90 else 2}
    elif ext == "png":
        if opts.png_reduce_colors:
            img = img.convert("RGBA").quantize(256, method=Image.FASTOCTREE)
        save = {"format": "PNG", "optimize": True, "compress_level": 9}
    elif ext == "webp":
        save = {"format": "WEBP", "quality": opts.quality, "method": 6}
    else:
        save = {}
    if exif and ext in ("jpg", "jpeg", "webp", "png"):
        save["exif"] = exif
    if icc and not opts.strip_metadata:
        save["icc_profile"] = icc

    dst = output_path(src, ext, opts.out_dir)
    img.save(dst, **save)
    return dst
