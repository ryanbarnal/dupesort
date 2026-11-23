"""Music workflow: find duplicate songs, look up tags/lyrics, rename files."""

from __future__ import annotations

import os
import re
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from ..core.duplicates import DuplicateGroup, merge_groups
from ..core.hashing import find_exact_duplicates
from ..core.history import Session
from ..core.scanner import FileEntry
from ..settings import Settings
from . import fingerprint, lookup
from .tags import audio_info, format_name, guess_from_filename, read_tags, write_tags

Progress = Optional[Callable[[int, int, str], None]]


def quality(f: FileEntry) -> tuple:
    i = f.info
    return (i.get("lossless", False), i.get("bitrate", 0), i.get("sample_rate", 0),
            len(i.get("tags", {})))


def load_info(files: list[FileEntry], progress: Progress = None,
              cancelled: Callable[[], bool] = lambda: False) -> None:
    for n, f in enumerate(files, 1):
        if cancelled():
            return
        f.info.update(audio_info(f.path))
        try:
            f.info["tags"] = read_tags(f.path)
        except Exception:
            f.info["tags"] = {}
        if progress and n % 20 == 0:
            progress(n, len(files), f"Reading tags: {f.path.name}")


# Words that mark a different recording or arrangement of a song. Two files
# with the same artist and title but a different set of these are kept apart.
_VERSION_WORDS = {
    "acoustic": r"acoustic|akustik|acustic[oa]|acoustique",
    "unplugged": r"unplugged",
    "live": r"live|en vivo|ao vivo|en directo|in concert|concert|en concierto|live at|tour",
    "demo": r"demo",
    "remix": r"remix|rmx|re ?mix|club mix|dub mix|extended mix|extended|bootleg|mash ?up|vip mix",
    "instrumental": r"instrumental|karaoke|backing track|minus one|off vocal",
    "a cappella": r"a ?cappella|acapella|vocals? only",
    "orchestral": r"orchestral|symphonic|orchestra|philharmonic",
    "piano": r"piano version|piano",
    "stripped": r"stripped|session|sessions",
    "cover": r"cover",
    "sped up": r"sped up|slowed|nightcore|reverb",
    "re-recorded": r"re ?recorded|taylor s version|new version|\d{4} version",
}
_VERSION_RE = {label: re.compile(rf"\b(?:{words})\b") for label, words in _VERSION_WORDS.items()}
# Bracketed notes that do NOT make a different version.
_NEUTRAL = re.compile(r"\b(?:remaster(?:ed)?|explicit|clean|mono|stereo|deluxe|bonus|"
                      r"album version|original version|original mix|single version|radio edit|"
                      r"official|audio|lyrics?|video|hq|hd|feat|ft|featuring)\b")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _title_extras(title: str) -> list[str]:
    """The notes around a title: ``(Live at Wembley)``, ``[Acoustic]``, ``- Demo``."""
    extras = re.findall(r"[\(\[]([^\)\]]*)[\)\]]", title or "")
    parts = re.split(r"\s+[-–—]\s+", re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", title or ""))
    return extras + parts[1:]


def version_of(f: FileEntry) -> frozenset[str]:
    """Which kind of recording ``f`` is: live, acoustic, remix… (empty = the normal one).

    Looks at notes in the title tag and the file name, and at the album, genre
    and folder name, e.g. "Song (Acoustic)", album "MTV Unplugged", genre
    "Live", or a folder called "Live in Concert 2004".
    """
    tags = f.info.get("tags") or {}
    # From the file name use only the title part, so "Oasis - Live Forever" is not "live".
    name_title = guess_from_filename(f.path).get("title", "")
    notes = _title_extras(tags.get("title", "")) + _title_extras(name_title)
    whole = [tags.get("album", ""), tags.get("genre", ""), f.path.parent.name]
    found: set[str] = set()
    for text in notes + whole:
        plain = _plain(text)
        if not plain:
            continue
        hits = {label for label, rx in _VERSION_RE.items() if rx.search(plain)}
        found |= hits
        # Any other "... version" / "... mix" note in the title names its own version,
        # e.g. "(Taylor's Version)" or "(Kygo Mix)", unless it is a neutral note.
        if not hits and text in notes and re.search(r"\b(?:version|mix|edit|take)\b", plain) \
                and not _NEUTRAL.search(plain):
            found.add(plain)
    return frozenset(found)


def _same_tags(files: list[FileEntry], separate_versions: bool = True) -> list[list[FileEntry]]:
    """Same normalized artist + title (and version) with durations within 3 seconds."""
    buckets: dict[tuple, list[FileEntry]] = defaultdict(list)
    for f in files:
        t = f.info.get("tags") or guess_from_filename(f.path)
        artist, title = lookup.normalize(t.get("artist", "")), lookup.normalize(t.get("title", ""))
        if artist and title:
            buckets[(artist, title, version_of(f) if separate_versions else None)].append(f)
    groups = []
    for bucket in buckets.values():
        bucket.sort(key=lambda f: f.info.get("duration", 0))
        current = [bucket[0]]
        for f in bucket[1:]:
            if f.info.get("duration", 0) - current[-1].info.get("duration", 0) <= 3:
                current.append(f)
            else:
                if len(current) > 1:
                    groups.append(current)
                current = [f]
        if len(current) > 1:
            groups.append(current)
    return groups


def _same_sound(files: list[FileEntry], threshold: float, progress: Progress,
                cancelled: Callable[[], bool],
                separate_versions: bool = True) -> list[list[FileEntry]]:
    """Compare Chromaprint fingerprints of songs with similar durations."""
    prints = {}
    # fpcalc runs as a separate process, so several can work in parallel.
    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2))) as pool:
        futures = {pool.submit(fingerprint.raw_fingerprint, f.path): f for f in files}
        for n, fut in enumerate(as_completed(futures), 1):
            if cancelled():
                for other in futures:
                    other.cancel()
                return []
            f, fp = futures[fut], fut.result()
            if fp:
                prints[str(f.path)] = fp[1]
                f.info.setdefault("duration", fp[0])
            if progress:
                progress(n, len(files), f"Fingerprinting: {f.path.name}")
    ordered = sorted((f for f in files if str(f.path) in prints),
                     key=lambda f: f.info.get("duration", 0))
    coarse = {k: fingerprint.coarse_set(v) for k, v in prints.items()}
    versions = {str(f.path): version_of(f) for f in ordered} if separate_versions else {}
    pairs = []
    for i, a in enumerate(ordered):
        ka = str(a.path)
        for b in ordered[i + 1:]:
            if b.info.get("duration", 0) - a.info.get("duration", 0) > 8:
                break
            kb = str(b.path)
            if versions and versions[ka] != versions[kb]:
                continue  # e.g. a live and a studio take can sound alike
            if fingerprint.may_match(coarse[ka], coarse[kb]) and \
                    fingerprint.similarity(prints[ka], prints[kb]) >= threshold:
                pairs.append([a, b])
    return pairs  # merge_groups joins overlapping pairs into clusters


def find_duplicates(files: list[FileEntry], settings: Settings, progress: Progress = None,
                    cancelled: Callable[[], bool] = lambda: False) -> list[DuplicateGroup]:
    load_info(files, progress, cancelled)
    found = [("Identical file", find_exact_duplicates(files, cancelled=cancelled))]
    if settings.music_match_by_tags:
        found.append(("Same artist & title",
                      _same_tags(files, settings.music_separate_versions)))
    if settings.music_match_by_fingerprint and fingerprint.available():
        found.append(("Same sound", _same_sound(files, 0.85, progress, cancelled,
                                                  settings.music_separate_versions)))
    return merge_groups(found)


def build_proposal(path: Path, settings: Settings) -> lookup.Proposal:
    """Look ``path`` up online and return suggested tags + lyrics."""
    try:
        current = read_tags(path)
    except Exception as exc:
        return lookup.Proposal(path, {}, error=str(exc))
    duration = audio_info(path)["duration"]
    prop = lookup.Proposal(path, current, duration)
    query = current if current.get("title") else {**guess_from_filename(path), **current}

    matches = lookup.search_acoustid(path, settings.acoustid_api_key)
    if not matches or matches[0].confidence < settings.auto_apply_confidence:
        matches += lookup.search_musicbrainz(query.get("artist", ""), query.get("title", ""),
                                             duration, query.get("album", ""))
    seen, unique = set(), []
    for m in sorted(matches, key=lambda m: -m.confidence):
        key = (lookup.normalize(m.tags.get("artist", "")), lookup.normalize(m.tags.get("title", "")),
               lookup.normalize(m.tags.get("album", "")))
        if key not in seen:
            seen.add(key)
            unique.append(m)
    prop.matches = unique[:8]
    if prop.match is None:
        prop.error = "No match found online"
        return prop

    best = prop.match
    if best.recording_id and "genre" not in best.tags:
        genre = lookup.genre_for(best.recording_id)
        if genre:
            best.tags["genre"] = genre
    if settings.fetch_lyrics and not current.get("lyrics"):
        t = prop.proposed()
        prop.lyrics = lookup.fetch_lyrics(t.get("artist", ""), t.get("title", ""),
                                          t.get("album", ""), duration)
    prop.apply = best.confidence >= settings.auto_apply_confidence
    return prop


def choose_match(prop: lookup.Proposal, index: int, settings: Settings) -> None:
    """Switch a proposal to another candidate, refreshing genre and lyrics."""
    prop.chosen = index
    m = prop.match
    if m and m.recording_id and "genre" not in m.tags:
        m.tags["genre"] = lookup.genre_for(m.recording_id) or ""
    if settings.fetch_lyrics and not prop.current.get("lyrics") and m:
        prop.lyrics = lookup.fetch_lyrics(m.tags.get("artist", ""), m.tags.get("title", ""),
                                          m.tags.get("album", ""), prop.duration)
    prop.apply = True


def apply_proposal(prop: lookup.Proposal, session: Session, settings: Settings,
                   rename: bool) -> Path:
    """Write the proposal's tags (and cover art) and optionally rename the file."""
    new = {k: v for k, v in prop.proposed().items() if v}
    cover = None
    if settings.fetch_cover_art and prop.match and prop.match.release_id:
        cover = lookup.fetch_cover(prop.match.release_id)
    write_tags(prop.path, new, cover=cover)
    session.record_tags(prop.path, prop.current, new)
    path = prop.path
    if rename:
        path = rename_file(path, settings.music_rename_pattern, session, new)
    return path


def rename_file(path: Path, pattern: str, session: Session, tags: Optional[dict] = None) -> Path:
    tags = tags if tags is not None else read_tags(path)
    name = format_name(pattern, tags, path.suffix.lower())
    if not name:
        return path
    # Undo replays newest-first, so the rename is reverted before any earlier
    # tag snapshot is restored at the original path.
    return session.rename(path, name)
