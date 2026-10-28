"""PDF tools: images <-> PDF, Office documents -> PDF, text, merge and compress."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageOps

from .. import photos  # noqa: F401  (HEIC support)
from ..tools import run
from . import output_path
from .ffmpeg import ConversionError

OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".txt", ".xls", ".xlsx", ".ods", ".csv",
               ".ppt", ".pptx", ".odp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"}
PAGE_SIZES = {"Fit to image": None, "A4": (8.27, 11.69), "Letter": (8.5, 11.0)}

Progress = Optional[Callable[[int, int], None]]


# --- images -> PDF -----------------------------------------------------------
def images_to_pdf(images: list[Path], dst: Path, page: str = "Fit to image",
                  dpi: int = 150, margin_in: float = 0.4, progress: Progress = None) -> Path:
    pages = []
    size = PAGE_SIZES[page]
    for n, path in enumerate(images, 1):
        with Image.open(path) as im:
            img = ImageOps.exif_transpose(im).convert("RGB")
        if size:
            pw, ph = int(size[0] * dpi), int(size[1] * dpi)
            if img.width > img.height:  # landscape photo -> landscape page
                pw, ph = ph, pw
            canvas = Image.new("RGB", (pw, ph), "white")
            m = int(margin_in * dpi)
            img.thumbnail((pw - 2 * m, ph - 2 * m), Image.LANCZOS)
            canvas.paste(img, ((pw - img.width) // 2, (ph - img.height) // 2))
            img = canvas
        pages.append(img)
        if progress:
            progress(n, len(images))
    if not pages:
        raise ConversionError("No images to convert.")
    pages[0].save(dst, "PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return dst


# --- PDF -> images -----------------------------------------------------------
def pdf_to_images(pdf: Path, out_dir: Path, fmt: str = "PNG", dpi: int = 150,
                  progress: Progress = None, cancelled: Callable[[], bool] = lambda: False
                  ) -> list[Path]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    out_dir = Path(out_dir) / pdf.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if fmt == "JPEG" else "png"
    written = []
    try:
        for i in range(len(doc)):
            if cancelled():
                break
            img = doc[i].render(scale=dpi / 72).to_pil()
            dst = out_dir / f"{pdf.stem} - page {i + 1:03d}.{ext}"
            if ext == "jpg":
                img.convert("RGB").save(dst, "JPEG", quality=90, optimize=True)
            else:
                img.save(dst, "PNG", optimize=True)
            written.append(dst)
            if progress:
                progress(i + 1, len(doc))
    finally:
        doc.close()
    return written


# --- Office -> PDF -----------------------------------------------------------
def find_libreoffice() -> Optional[str]:
    for name in ("soffice", "libreoffice"):
        hit = shutil.which(name)
        if hit:
            return hit
    for c in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
              r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/usr/bin/soffice", "/snap/bin/libreoffice"):
        if Path(c).exists():
            return c
    return None


_PS_OFFICE = r"""
$ErrorActionPreference = 'Stop'
$src = $args[0]; $dst = $args[1]; $ext = [IO.Path]::GetExtension($src).ToLower()
if ($ext -in '.doc','.docx','.rtf','.odt','.txt') {
  $app = New-Object -ComObject Word.Application; $app.Visible = $false
  try { $d = $app.Documents.Open($src, $false, $true); $d.SaveAs([ref]$dst, [ref]17); $d.Close($false) }
  finally { $app.Quit() }
} elseif ($ext -in '.xls','.xlsx','.ods','.csv') {
  $app = New-Object -ComObject Excel.Application; $app.Visible = $false; $app.DisplayAlerts = $false
  try { $w = $app.Workbooks.Open($src, 0, $true); $w.ExportAsFixedFormat(0, $dst); $w.Close($false) }
  finally { $app.Quit() }
} elseif ($ext -in '.ppt','.pptx','.odp') {
  $app = New-Object -ComObject PowerPoint.Application
  try { $p = $app.Presentations.Open($src, $true, $false, $false); $p.SaveAs($dst, 32); $p.Close() }
  finally { $app.Quit() }
} else { throw "Unsupported file type" }
"""


def office_available() -> str:
    """'' if nothing can convert Office files, else a short description."""
    if find_libreoffice():
        return "LibreOffice"
    if sys.platform == "win32" and shutil.which("powershell"):
        try:
            import winreg  # noqa: F401

            for prog in ("Word.Application", "Excel.Application", "PowerPoint.Application"):
                try:
                    winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog)
                    return "Microsoft Office"
                except OSError:
                    continue
        except ImportError:
            pass
    return ""


def office_to_pdf(src: Path, out_dir: Optional[Path] = None) -> Path:
    dst = output_path(src, "pdf", out_dir)
    soffice = find_libreoffice()
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            # A private profile lets this run even while LibreOffice is open.
            profile = Path(tmp, "profile").as_uri()
            res = run([soffice, f"-env:UserInstallation={profile}", "--headless",
                       "--convert-to", "pdf", "--outdir", tmp, str(src)], timeout=300)
            produced = Path(tmp) / (src.stem + ".pdf")
            if res.returncode != 0 or not produced.exists():
                raise ConversionError("LibreOffice could not convert this file.")
            shutil.move(str(produced), str(dst))
        return dst
    if sys.platform == "win32" and office_available():
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False) as f:
            f.write(_PS_OFFICE)
            script = f.name
        try:
            res = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                       script, str(src.resolve()), str(dst.resolve())], timeout=300)
        finally:
            os.unlink(script)
        if res.returncode != 0 or not dst.exists():
            raise ConversionError("Microsoft Office could not convert this file.")
        return dst
    raise ConversionError("Converting Word, Excel and PowerPoint files needs the free "
                          "LibreOffice (libreoffice.org)" +
                          (" or Microsoft Office" if sys.platform == "win32" else "") + ".")


# --- text, merge, compress -----------------------------------------------------
def pdf_to_text(pdf: Path, out_dir: Optional[Path] = None) -> Path:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    text = "\n\n".join(f"--- Page {i + 1} ---\n{(p.extract_text() or '').strip()}"
                       for i, p in enumerate(reader.pages))
    dst = output_path(pdf, "txt", out_dir)
    dst.write_text(text, encoding="utf-8")
    return dst


def merge_pdfs(pdfs: list[Path], dst: Path, progress: Progress = None) -> Path:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for n, p in enumerate(pdfs, 1):
        writer.append(str(p))
        if progress:
            progress(n, len(pdfs))
    with open(dst, "wb") as f:
        writer.write(f)
    return dst


def compress_pdf(pdf: Path, out_dir: Optional[Path] = None, image_quality: int = 60,
                 max_image_side: int = 1600) -> tuple[Path, int, int]:
    """Re-compress embedded images and streams. Returns (path, old size, new size)."""
    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=str(pdf))
    seen = set()
    for page in writer.pages:
        for image in page.images:
            key = getattr(image, "indirect_reference", None)
            if key is not None and key in seen:
                continue
            seen.add(key)
            try:
                img = image.image
                if img is None or img.width * img.height < 40_000:
                    continue  # tiny icons/logos: not worth it
                if max(img.size) > max_image_side:
                    img = img.copy()
                    img.thumbnail((max_image_side, max_image_side), Image.LANCZOS)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                image.replace(img, quality=image_quality)
            except Exception:
                continue  # unusual image encodings are left as they are
        page.compress_content_streams()
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    dst = output_path(pdf, "pdf", out_dir, " (compressed)")
    with open(dst, "wb") as f:
        writer.write(f)
    old, new = pdf.stat().st_size, dst.stat().st_size
    if new >= old:  # nothing gained; keep the original's bytes
        shutil.copyfile(pdf, dst)
        new = old
    return dst, old, new
