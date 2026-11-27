"""Read and write song tags (including lyrics and cover art) for common formats."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Optional

import mutagen
from mutagen.apev2 import APEv2
from mutagen.asf import ASF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, USLT
from mutagen.mp4 import MP4, MP4Cover
from ..core.longpath import lp

FIELDS = ("title", "artist", "album", "albumartist", "genre", "date", "tracknumber", "lyrics")
LOSSLESS = {".flac", ".wav", ".aiff", ".aif", ".ape", ".wv", ".alac"}

_ID3 = {"title": TIT2, "artist": TPE1, "album": TALB, "albumartist": TPE2,
        "genre": TCON, "date": TDRC, "tracknumber": TRCK}
_MP4 = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "albumartist": "aART",
        "genre": "\xa9gen", "date": "\xa9day", "lyrics": "\xa9lyr"}
_ASF = {"title": "Title", "artist": "Author", "album": "WM/AlbumTitle",
        "albumartist": "WM/AlbumArtist", "genre": "WM/Genre", "date": "WM/Year",
        "tracknumber": "WM/TrackNumber", "lyrics": "WM/Lyrics"}
_APE = {"title": "Title", "artist": "Artist", "album": "Album", "albumartist": "Album Artist",
        "genre": "Genre", "date": "Year", "tracknumber": "Track", "lyrics": "Lyrics"}


def _open(path: Path):
    audio = mutagen.File(lp(path))
    if audio is None:
        raise ValueError(f"Unsupported audio file: {path.name}")
    return audio


def _kind(audio) -> str:
    if isinstance(audio, MP4):
        return "mp4"
    if isinstance(audio, ASF):
        return "asf"
    if isinstance(audio.tags, ID3) or audio.tags is None and hasattr(audio, "add_tags") \
            and type(audio).__name__ in {"MP3", "WAVE", "AIFF", "TrueAudio", "DSF"}:
        return "id3"
    if isinstance(audio.tags, APEv2) or type(audio).__name__ in {"MonkeysAudio", "WavPack", "Musepack"}:
        return "ape"
    return "vorbis"


def read_tags(path: Path) -> dict:
    """Return the text tags of ``path`` as ``{field: str}`` (missing fields omitted)."""
    audio = _open(path)
    kind, tags, out = _kind(audio), audio.tags, {}
    if tags is None:
        return out
    if kind == "id3":
        for name, frame in _ID3.items():
            if frame.__name__ in tags:
                out[name] = str(tags[frame.__name__].text[0])
        uslt = tags.getall("USLT")
        if uslt:
            out["lyrics"] = uslt[0].text
    elif kind == "mp4":
        for name, key in _MP4.items():
            if key in tags:
                out[name] = str(tags[key][0])
        if "trkn" in tags and tags["trkn"][0][0]:
            out["tracknumber"] = str(tags["trkn"][0][0])
    elif kind in ("asf", "ape"):
        mapping = _ASF if kind == "asf" else _APE
        for name, key in mapping.items():
            if key in tags:
                out[name] = str(tags[key][0])
    else:
        for name in FIELDS:
            if name in tags:
                out[name] = str(tags[name][0])
    return {k: v for k, v in out.items() if v and v.strip()}


def read_cover(path: Path) -> Optional[bytes]:
    """The embedded front-cover image (JPEG/PNG bytes), if any."""
    audio = _open(path)
    kind, tags = _kind(audio), audio.tags
    if isinstance(audio, FLAC) and audio.pictures:
        return audio.pictures[0].data
    if tags is None:
        return None
    if kind == "id3":
        pics = tags.getall("APIC")
        return pics[0].data if pics else None
    if kind == "mp4":
        covers = tags.get("covr")
        return bytes(covers[0]) if covers else None
    if kind == "vorbis" and "metadata_block_picture" in tags:
        try:
            return Picture(base64.b64decode(tags["metadata_block_picture"][0])).data
        except Exception:
            return None
    return None


def audio_info(path: Path) -> dict:
    """Duration (s), bitrate (bps), sample rate and lossless flag for ranking copies."""
    try:
        info = _open(path).info
    except Exception:
        return {"duration": 0.0, "bitrate": 0, "sample_rate": 0, "lossless": False}
    return {
        "duration": float(getattr(info, "length", 0) or 0),
        "bitrate": int(getattr(info, "bitrate", 0) or 0),
        "sample_rate": int(getattr(info, "sample_rate", 0) or 0),
        "lossless": path.suffix.lower() in LOSSLESS,
    }


def write_tags(path: Path, values: dict, clear_missing: bool = False,
               cover: Optional[bytes] = None) -> None:
    """Write text ``values`` (see ``FIELDS``) and optional JPEG/PNG ``cover``.

    With ``clear_missing`` every field in ``FIELDS`` not present in ``values``
    is removed - used to restore an exact earlier snapshot on undo.
    """
    audio = _open(path)
    if audio.tags is None:
        audio.add_tags()
    kind, tags = _kind(audio), audio.tags
    targets = {f: values.get(f) for f in FIELDS if f in values or clear_missing}
    mime = "image/png" if cover and cover[:4] == b"\x89PNG" else "image/jpeg"

    if kind == "id3":
        for name, value in targets.items():
            if name == "lyrics":
                tags.delall("USLT")
                if value:
                    tags.add(USLT(encoding=3, lang="eng", desc="", text=value))
                continue
            frame = _ID3[name]
            tags.delall(frame.__name__)
            if value:
                tags.add(frame(encoding=3, text=[value]))
        if cover:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
    elif kind == "mp4":
        for name, value in targets.items():
            if name == "tracknumber":
                key = "trkn"
                num = re.match(r"\d+", value or "")
                value = [(int(num.group()), 0)] if num else None
            else:
                key = _MP4[name]
                value = [value] if value else None
            if value:
                tags[key] = value
            elif key in tags:
                del tags[key]
        if cover:
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            tags["covr"] = [MP4Cover(cover, imageformat=fmt)]
    elif kind in ("asf", "ape"):
        mapping = _ASF if kind == "asf" else _APE
        for name, value in targets.items():
            key = mapping[name]
            if value:
                tags[key] = [value] if kind == "asf" else value
            elif key in tags:
                del tags[key]
    else:  # Vorbis comments: FLAC, Ogg Vorbis, Opus, Speex
        for name, value in targets.items():
            if value:
                tags[name] = [value]
            elif name in tags:
                del tags[name]
        if cover:
            pic = Picture()
            pic.type, pic.mime, pic.desc, pic.data = 3, mime, "Cover", cover
            if isinstance(audio, FLAC):
                audio.clear_pictures()
                audio.add_picture(pic)
            else:
                tags["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
    audio.save()


_TRACK_PREFIX = re.compile(r"^\s*(?:\d{1,3}|[A-D]\d{1,2})\s*[-._)\]]?\s+")


def guess_from_filename(path: Path) -> dict:
    """Best-effort artist/title from names like ``03 - Artist - Title.mp3``."""
    stem = _TRACK_PREFIX.sub("", path.stem)
    stem = re.sub(r"[\[(](?:official.*?|lyrics?|audio|hq|hd|\d{3,4}p)[\])]", "", stem, flags=re.I)
    stem = stem.replace("_", " ").strip()
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", stem) if p.strip()]
    if len(parts) >= 2:
        return {"artist": parts[0], "title": " - ".join(parts[1:])}
    return {"title": stem} if stem else {}


def format_name(pattern: str, tags: dict, ext: str) -> Optional[str]:
    """Render ``pattern`` (e.g. ``{artist} - {title}``) or None if a field is missing."""
    try:
        name = pattern.format_map({k: (v or "").strip() for k, v in tags.items()
                                   if k != "lyrics"})
    except (KeyError, ValueError, IndexError):
        return None
    name = name.strip(" -")
    return name + ext if name else None
