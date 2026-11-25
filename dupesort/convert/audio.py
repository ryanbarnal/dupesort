"""Convert songs between formats and bitrates, keeping tags, lyrics and cover art."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..music.tags import LOSSLESS, audio_info, read_cover, read_tags, write_tags
from ..core.history import Session, unique_path
from ..core.scanner import CONVERTED_DIR
from . import output_path, record_conversion
from .ffmpeg import ConversionError, convert, pick_encoder, remove_partial

# name: (extension, encoders to try, uses a bitrate)
FORMATS = {
    "MP3": ("mp3", ("libmp3lame",), True),
    "AAC (M4A)": ("m4a", ("aac_at", "aac"), True),
    "Opus": ("opus", ("libopus",), True),
    "Ogg Vorbis": ("ogg", ("libvorbis",), True),
    "FLAC (lossless)": ("flac", ("flac",), False),
    "ALAC (Apple lossless)": ("m4a", ("alac",), False),
    "WAV (uncompressed)": ("wav", ("pcm_s16le",), False),
}
BITRATES = (64, 96, 128, 160, 192, 256, 320)


@dataclass
class AudioOptions:
    fmt: str = "MP3"
    bitrate: int = 192  # kbps, lossy formats only
    no_upscale: bool = True  # never raise the bitrate above the source's
    sample_rate: int = 0  # 0 = keep
    mono: bool = False
    out_dir: Optional[Path] = None
    # History session for replacing originals in place (so it can be undone).
    session: Optional[Session] = None


def convert_audio(src: Path, opts: AudioOptions,
                  progress: Optional[Callable[[float], None]] = None,
                  cancelled: Callable[[], bool] = lambda: False) -> Path:
    ext, encs, lossy = FORMATS[opts.fmt]
    info = audio_info(src)
    args = ["-i", str(src), "-map", "0:a:0", "-map_metadata", "-1", "-vn",
            "-c:a", pick_encoder(*encs)]
    if lossy:
        kbps = opts.bitrate
        source_kbps = info["bitrate"] // 1000
        if opts.no_upscale and source_kbps and not info["lossless"]:
            # Re-encoding at a higher bitrate only makes the file bigger. Snap the
            # cap to a standard rate (measured bitrates read e.g. 95 for 96).
            cap = max([b for b in BITRATES if b <= source_kbps + 8] or [BITRATES[0]])
            kbps = min(kbps, cap)
        args += ["-b:a", f"{kbps}k"]
    if opts.fmt == "Opus":
        args += ["-ar", "48000"]  # Opus only supports 48 kHz output
    elif opts.sample_rate:
        args += ["-ar", str(opts.sample_rate)]
    if opts.mono:
        args += ["-ac", "1"]
    folder = Path(opts.out_dir) if opts.out_dir else src.parent
    # Same folder and same format: the converted file takes the original's name and place.
    # It's made in _Converted first; the original then moves into _Converted (History can
    # undo both), so nothing is lost and the names stay clean.
    replace = (folder / f"{src.stem}.{ext}").resolve() == src.resolve()
    if replace:
        dst = unique_path(src.parent / CONVERTED_DIR / f"{src.stem} (new).{ext}")
        dst.parent.mkdir(parents=True, exist_ok=True)
    else:
        dst = output_path(src, ext, opts.out_dir)
    try:
        convert(args + [str(dst)], info["duration"], progress, cancelled)
    except ConversionError:
        remove_partial(dst)
        if replace:
            try:
                dst.parent.rmdir()  # only if it is empty
            except OSError:
                pass
        raise
    # Copy tags, lyrics and cover art with mutagen (FFmpeg loses some of them).
    try:
        tags = read_tags(src)
        cover = read_cover(src)
        if tags or cover:
            write_tags(dst, tags, cover=cover)
    except Exception:
        pass  # the audio itself converted fine; tags are best effort
    if replace:
        session = opts.session or Session(f"Converted {src.name}")
        original = session.move(src, src.parent / CONVERTED_DIR / src.name)
        dst = session.move(dst, src)
        record_conversion(original, dst)
    else:
        record_conversion(src, dst)
    return dst


def describe_source(path: Path) -> str:
    i = audio_info(path)
    kind = "lossless" if path.suffix.lower() in LOSSLESS else f"{i['bitrate'] // 1000} kbps"
    return f"{path.suffix[1:].upper()} · {kind}"
