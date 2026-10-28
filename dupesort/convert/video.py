"""Convert videos: container/codec, resolution, aspect ratio and file size."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import output_path
from .ffmpeg import ConversionError, convert, duration_of, pick_encoder, probe, remove_partial

CONTAINERS = ("MP4", "MOV", "MKV", "WebM", "AVI")
CODECS = ("H.264 (most compatible)", "H.265 / HEVC (smaller)", "VP9", "AV1 (smallest, slow)")
RESOLUTIONS = {"Keep": 0, "4K (2160p)": 2160, "1440p": 1440, "1080p": 1080, "720p": 720,
               "480p": 480, "360p": 360}
ASPECTS = {"Keep": None, "16:9 (widescreen)": (16, 9), "9:16 (vertical / Reels)": (9, 16),
           "4:3": (4, 3), "1:1 (square)": (1, 1), "4:5 (portrait post)": (4, 5),
           "21:9 (cinema)": (21, 9)}
ASPECT_MODES = ("Fit (add black bars)", "Fill (crop edges)", "Stretch")
QUALITY = {"High quality": 0, "Balanced": 1, "Small file": 2}

# Constant-quality values per codec for High / Balanced / Small.
_CRF = {"h264": (18, 23, 28), "hevc": (22, 27, 32), "vp9": (28, 34, 40), "av1": (28, 35, 42)}


@dataclass
class VideoOptions:
    container: str = "MP4"
    codec: str = "H.264 (most compatible)"
    resolution: str = "Keep"
    aspect: str = "Keep"
    aspect_mode: str = "Fit (add black bars)"
    quality: str = "Balanced"
    out_dir: Optional[Path] = None


def _codec_family(opts: VideoOptions) -> str:
    if opts.container == "WebM":
        return "av1" if opts.codec.startswith("AV1") else "vp9"
    if opts.container == "AVI":
        return "mpeg4"
    for prefix, family in (("H.264", "h264"), ("H.265", "hevc"), ("VP9", "vp9"), ("AV1", "av1")):
        if opts.codec.startswith(prefix):
            return family
    return "h264"


def _video_args(family: str, level: int) -> list[str]:
    if family == "h264":
        enc = pick_encoder("libx264", "h264_videotoolbox", "h264_mf", "libopenh264", "mpeg4")
    elif family == "hevc":
        enc = pick_encoder("libx265", "hevc_videotoolbox", "hevc_mf", "libx264", "mpeg4")
    elif family == "vp9":
        enc = pick_encoder("libvpx-vp9", "libaom-av1", "mpeg4")
    elif family == "av1":
        enc = pick_encoder("libsvtav1", "libaom-av1", "libvpx-vp9", "mpeg4")
    else:
        enc = "mpeg4"
    args = ["-c:v", enc]
    if enc in ("libx264", "libx265"):
        args += ["-crf", str(_CRF["h264" if enc == "libx264" else "hevc"][level]),
                 "-preset", "medium"]
        if enc == "libx265":
            args += ["-tag:v", "hvc1"]  # lets Apple devices play it
    elif enc in ("libvpx-vp9",):
        args += ["-crf", str(_CRF["vp9"][level]), "-b:v", "0", "-row-mt", "1"]
    elif enc == "libsvtav1":
        args += ["-crf", str(_CRF["av1"][level]), "-preset", "8"]
    elif enc == "libaom-av1":
        args += ["-crf", str(_CRF["av1"][level]), "-b:v", "0", "-cpu-used", "6",
                 "-row-mt", "1"]
    elif enc.endswith(("_videotoolbox", "_mf")) or enc == "libopenh264":
        args += ["-b:v", ("8M", "4M", "1500k")[level]]
        if enc == "hevc_videotoolbox":
            args += ["-tag:v", "hvc1"]
    else:  # mpeg4
        args += ["-q:v", str((3, 5, 9)[level])]
    return args + ["-pix_fmt", "yuv420p"]


def _audio_args(container: str, level: int) -> list[str]:
    kbps = ("192k", "160k", "96k")[level]
    if container == "WebM":
        return ["-c:a", pick_encoder("libopus", "libvorbis"), "-b:a", kbps]
    if container == "AVI":
        return ["-c:a", pick_encoder("libmp3lame", "aac"), "-b:a", kbps]
    return ["-c:a", pick_encoder("aac_at", "aac"), "-b:a", kbps]


def target_size(src_w: int, src_h: int, short_side: int,
                aspect: Optional[tuple]) -> tuple[int, int]:
    """Output (width, height): ``short_side`` 0 keeps the source's shorter side."""
    short = short_side or min(src_w, src_h)
    if aspect is None:
        if src_w >= src_h:
            w, h = src_w * short / src_h, short
        else:
            w, h = short, src_h * short / src_w
    else:
        aw, ah = aspect
        w, h = (short * aw / ah, short) if aw >= ah else (short, short * ah / aw)
    return int(round(w / 2) * 2), int(round(h / 2) * 2)


def build_filter(src_w: int, src_h: int, opts: VideoOptions) -> Optional[str]:
    aspect = ASPECTS[opts.aspect]
    short = RESOLUTIONS[opts.resolution]
    if aspect is None and not short:
        return None
    w, h = target_size(src_w, src_h, short, aspect)
    if aspect is None:
        return f"scale={w}:{h}:flags=lanczos,setsar=1"
    if opts.aspect_mode.startswith("Fit"):
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    if opts.aspect_mode.startswith("Fill"):
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h},setsar=1")
    return f"scale={w}:{h}:flags=lanczos,setsar=1"


def convert_video(src: Path, opts: VideoOptions,
                  progress: Optional[Callable[[float], None]] = None,
                  cancelled: Callable[[], bool] = lambda: False) -> Path:
    info = probe(src)
    vstream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not vstream:
        raise ConversionError("No video stream found (is FFmpeg installed?).")
    w, h = int(vstream.get("width") or 0), int(vstream.get("height") or 0)
    rotation = 0
    for sd in vstream.get("side_data_list") or []:
        rotation = int(sd.get("rotation") or 0)
    if abs(rotation) in (90, 270):  # FFmpeg auto-rotates, so swap dimensions
        w, h = h, w
    level = QUALITY[opts.quality]
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))

    args = ["-i", str(src), "-map", "0:v:0", "-map_metadata", "0"]
    if has_audio:
        args += ["-map", "0:a:0"]
    vf = build_filter(w, h, opts)
    if vf:
        args += ["-vf", vf]
    args += _video_args(_codec_family(opts), level)
    if has_audio:
        args += _audio_args(opts.container, level)
    if opts.container in ("MP4", "MOV"):
        args += ["-movflags", "+faststart"]
    ext = {"MP4": "mp4", "MOV": "mov", "MKV": "mkv", "WebM": "webm", "AVI": "avi"}[opts.container]
    dst = output_path(src, ext, opts.out_dir)
    try:
        convert(args + [str(dst)], duration_of(info), progress, cancelled)
    except ConversionError:
        remove_partial(dst)
        raise
    return dst
