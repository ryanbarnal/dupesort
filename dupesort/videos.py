"""Videos: exact and re-encoded duplicates, recording dates, TMDb movie/TV names."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import imagehash
from PIL import Image

from . import web
from .core.duplicates import DuplicateGroup, merge_groups
from .core.hashing import find_exact_duplicates
from .core.history import Session, safe_filename
from .core.scanner import FileEntry
from .core.similar import hamming
from .settings import Settings
from .tools import find_tool, run

SAMPLE_POINTS = (0.1, 0.3, 0.5, 0.7, 0.9)
Progress = Optional[Callable[[int, int, str], None]]


def ffmpeg_available() -> bool:
    return bool(find_tool("ffprobe") and find_tool("ffmpeg"))


def probe(f: FileEntry) -> None:
    """Fill duration, resolution, bitrate and creation date from ffprobe."""
    exe = find_tool("ffprobe")
    if not exe:
        return
    try:
        out = run([exe, "-v", "quiet", "-print_format", "json", "-show_format",
                   "-show_streams", str(f.path)], timeout=60).stdout
        data = json.loads(out or b"{}")
    except (OSError, ValueError):
        return
    fmt = data.get("format", {})
    f.info["duration"] = float(fmt.get("duration") or 0)
    f.info["bitrate"] = int(fmt.get("bit_rate") or 0)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and s.get("width"):
            f.info["width"], f.info["height"] = s["width"], s["height"]
            f.info["codec"] = s.get("codec_name", "")
            break
    created = (fmt.get("tags") or {}).get("creation_time") or \
              (fmt.get("tags") or {}).get("com.apple.quicktime.creationdate")
    if created:
        try:
            f.info["date"] = datetime.fromisoformat(created.replace("Z", "+00:00")[:19])
        except ValueError:
            pass


def frame_hashes(f: FileEntry) -> list[int]:
    """Perceptual hashes of a handful of frames spread across the video."""
    exe, duration = find_tool("ffmpeg"), f.info.get("duration", 0)
    if not exe or duration <= 0:
        return []
    hashes = []
    for point in SAMPLE_POINTS:
        try:
            png = run([exe, "-v", "quiet", "-ss", f"{duration * point:.2f}", "-i", str(f.path),
                       "-frames:v", "1", "-vf", "scale=128:-2", "-f", "image2pipe",
                       "-vcodec", "png", "-"], timeout=60).stdout
            with Image.open(io.BytesIO(png)) as img:
                hashes.append(int(str(imagehash.phash(img.convert("L"))), 16))
        except Exception:
            return []
    return hashes


def quality(f: FileEntry) -> tuple:
    i = f.info
    return (i.get("width", 0) * i.get("height", 0), i.get("bitrate", 0))


def find_duplicates(files: list[FileEntry], settings: Settings, progress: Progress = None,
                    cancelled: Callable[[], bool] = lambda: False) -> list[DuplicateGroup]:
    found = [("Identical file", find_exact_duplicates(files, cancelled=cancelled))]
    if not ffmpeg_available():
        return merge_groups(found)
    for n, f in enumerate(files, 1):
        if cancelled():
            return merge_groups(found)
        probe(f)
        f.info["frames"] = frame_hashes(f)
        if progress:
            progress(n, len(files), f"Analysing: {f.path.name}")
    ordered = sorted((f for f in files if f.info.get("frames")),
                     key=lambda f: f.info["duration"])
    pairs = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b.info["duration"] - a.info["duration"] > max(2.0, a.info["duration"] * 0.01):
                break
            dist = sum(hamming(x, y) for x, y in zip(a.info["frames"], b.info["frames"]))
            if dist / len(SAMPLE_POINTS) <= settings.video_threshold:
                pairs.append([a, b])
    found.append(("Same video", pairs))
    return merge_groups(found)


# --- Movie / TV identification -------------------------------------------

_JUNK = re.compile(
    r"\b(2160p|1080p|720p|480p|4k|uhd|hdr|bluray|blu-ray|brrip|bdrip|webrip|web-dl|web|"
    r"hdtv|dvdrip|x264|x265|h264|h265|hevc|aac|ac3|dts|remux|proper|repack|extended|"
    r"unrated|10bit)\b.*", re.I)
_TV = re.compile(r"^(?P<show>.*?)[\s._-]+(?:s(?P<s>\d{1,2})[\s._-]*e(?P<e>\d{1,3})|"
                 r"(?P<s2>\d{1,2})x(?P<e2>\d{2,3}))\b", re.I)
_YEAR = re.compile(r"^(?P<title>.*?)[\s._(\[-]+(?P<year>(?:19|20)\d{2})\b")


def parse_name(path: Path) -> dict:
    """Guess ``{"kind": "tv"|"movie", ...}`` from a release-style filename."""
    stem = path.stem
    m = _TV.match(stem)
    if m:
        show = re.sub(r"[._]+", " ", m.group("show")).strip(" -")
        return {"kind": "tv", "title": show,
                "season": int(m.group("s") or m.group("s2")),
                "episode": int(m.group("e") or m.group("e2"))}
    m = _YEAR.match(stem)
    if m:
        title = re.sub(r"[._]+", " ", m.group("title")).strip(" -([")
        return {"kind": "movie", "title": title, "year": int(m.group("year"))}
    title = re.sub(r"[._]+", " ", _JUNK.sub("", stem)).strip(" -")
    return {"kind": "movie", "title": title}


@dataclass
class VideoProposal:
    path: Path
    guess: dict
    new_name: str = ""
    description: str = ""
    apply: bool = False
    error: str = ""


def _tmdb(path: str, key: str, params: dict) -> Optional[dict]:
    params = dict(params)
    headers = None
    if key.startswith("eyJ"):  # v4 read-access token
        headers = {"Authorization": f"Bearer {key}"}
    else:
        params["api_key"] = key
    return web.get_json(f"https://api.themoviedb.org/3/{path}", params, headers=headers)


def identify(path: Path, api_key: str) -> VideoProposal:
    guess = parse_name(path)
    prop = VideoProposal(path, guess)
    if not guess.get("title"):
        prop.error = "Could not read a title from the filename"
        return prop
    ext = path.suffix.lower()
    if guess["kind"] == "tv":
        data = _tmdb("search/tv", api_key, {"query": guess["title"]}) or {}
        results = data.get("results") or []
        if not results:
            prop.error = "Show not found on TMDb"
            return prop
        show = results[0]
        ep = _tmdb(f"tv/{show['id']}/season/{guess['season']}/episode/{guess['episode']}",
                   api_key, {}) or {}
        name = f"{show['name']} - S{guess['season']:02d}E{guess['episode']:02d}"
        if ep.get("name"):
            name += f" - {ep['name']}"
        prop.new_name, prop.description = name + ext, (ep.get("overview") or show.get("overview", ""))
    else:
        params = {"query": guess["title"]}
        if guess.get("year"):
            params["year"] = guess["year"]
        data = _tmdb("search/movie", api_key, params) or {}
        results = data.get("results") or []
        if not results:
            prop.error = "Movie not found on TMDb"
            return prop
        movie = results[0]
        year = (movie.get("release_date") or "")[:4]
        prop.new_name = f"{movie['title']} ({year}){ext}" if year else f"{movie['title']}{ext}"
        prop.description = movie.get("overview", "")
    prop.new_name = safe_filename(prop.new_name)
    prop.apply = prop.new_name != path.name
    return prop


def apply_rename(prop: VideoProposal, session: Session) -> Path:
    return session.rename(prop.path, prop.new_name)
