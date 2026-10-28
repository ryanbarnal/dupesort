"""Look songs up online: MusicBrainz (tags), AcoustID (fingerprint match),
Cover Art Archive (album art) and LRCLIB (lyrics). All are free services."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .. import web

MB = "https://musicbrainz.org/ws/2"


@dataclass
class Match:
    confidence: int  # 0-100
    tags: dict
    recording_id: str = ""
    release_id: str = ""
    source: str = "MusicBrainz"
    artist_id: str = ""

    def label(self) -> str:
        t = self.tags
        bits = [t.get("artist", "?"), t.get("title", "?")]
        if t.get("album"):
            bits.append(t["album"])
        if t.get("date"):
            bits.append(t["date"][:4])
        return f"{self.confidence}%  " + " - ".join(bits)


def normalize(text: str) -> str:
    """Lowercase, strip accents, 'feat.' credits and bracketed extras."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    text = re.sub(r"\b(feat|ft|featuring)\b.*", " ", text)
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _ratio(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _artist_credit(credits: list) -> str:
    return "".join(c.get("name", "") + c.get("joinphrase", "") for c in credits or []).strip()


def _pick_release(releases: list) -> Optional[dict]:
    """Prefer official studio albums, then the earliest date."""
    def rank(rel: dict):
        group = rel.get("release-group", {})
        return (
            rel.get("status") == "Official",
            group.get("primary-type") == "Album",
            not group.get("secondary-types"),
            -int((rel.get("date") or "9999")[:4] or 9999),
        )
    return max(releases, key=rank) if releases else None


def _recording_to_tags(rec: dict) -> tuple[dict, str]:
    tags = {"title": rec.get("title", ""), "artist": _artist_credit(rec.get("artist-credit"))}
    release = _pick_release(rec.get("releases") or [])
    release_id = ""
    if release:
        release_id = release.get("id", "")
        tags["album"] = release.get("title", "")
        tags["albumartist"] = _artist_credit(release.get("artist-credit")) or tags["artist"]
        if release.get("date"):
            tags["date"] = release["date"][:4]
        media = release.get("media") or []
        if media and media[0].get("track"):
            num = media[0]["track"][0].get("number", "")
            if num.isdigit():
                tags["tracknumber"] = num
    elif rec.get("first-release-date"):
        tags["date"] = rec["first-release-date"][:4]
    return {k: v for k, v in tags.items() if v}, release_id


@lru_cache(maxsize=2048)
def _artist_genre(artist_id: str) -> str:
    data = web.get_json(f"{MB}/artist/{artist_id}", {"inc": "genres", "fmt": "json"}) or {}
    genres = sorted(data.get("genres") or [], key=lambda g: -g.get("count", 0))
    return genres[0]["name"].title() if genres else ""


def genre_for(recording_id: str) -> str:
    data = web.get_json(f"{MB}/recording/{recording_id}",
                        {"inc": "genres+artist-credits", "fmt": "json"}) or {}
    genres = sorted(data.get("genres") or [], key=lambda g: -g.get("count", 0))
    if genres:
        return genres[0]["name"].title()
    credits = data.get("artist-credit") or []
    if credits and credits[0].get("artist", {}).get("id"):
        return _artist_genre(credits[0]["artist"]["id"])
    return ""


_VERSION_WORDS = re.compile(r"\b(remix|mix|live|edit|version|excerpt|instrumental|acoustic|"
                           r"karaoke|demo|cover|bootleg|remaster(?:ed)?|mono|stereo)\b", re.I)
_STUDIO_FILTER = (" AND primarytype:album AND status:official"
                  " AND NOT secondarytype:compilation AND NOT secondarytype:live"
                  " AND NOT secondarytype:dj-mix AND NOT secondarytype:remix")


def _is_studio(release: Optional[dict]) -> bool:
    group = (release or {}).get("release-group", {})
    return (release or {}).get("status") == "Official" and \
        group.get("primary-type") == "Album" and not group.get("secondary-types")


def search_musicbrainz(artist: str, title: str, duration: float = 0,
                       album: str = "", limit: int = 25) -> list[Match]:
    """Search recordings by artist/title and score how well each fits.

    MusicBrainz ranks every compilation, remix and live take equally high, so
    results are re-ranked: unrequested versions ("remix", "live" …) lose
    points, and among equal scores the recording found on an original studio
    album (and on the most releases) wins. If no studio-album recording turns
    up, a second search restricted to studio albums is made.
    """
    if not title:
        return []

    def esc(s: str) -> str:
        return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s)

    query = f'recording:"{esc(title)}"'
    if artist:
        query += f' AND artist:"{esc(artist)}"'
    wanted_versions = {w.lower() for w in _VERSION_WORDS.findall(title)}

    ranked: dict[str, tuple] = {}
    for q in (query, query + _STUDIO_FILTER):
        data = web.get_json(f"{MB}/recording", {"query": q, "limit": limit, "fmt": "json"})
        for rec in (data or {}).get("recordings", []):
            if rec.get("id") in ranked:
                continue
            tags, release_id = _recording_to_tags(rec)
            # Blend MusicBrainz's own score with how closely the names match.
            name_fit = _ratio(title, tags.get("title", ""))
            if artist:
                name_fit = (name_fit + _ratio(artist, tags.get("artist", ""))) / 2
            score = min(int(rec.get("score", 0)), int(name_fit * 100))
            extra = {w.lower() for w in _VERSION_WORDS.findall(tags.get("title", ""))}
            if extra - wanted_versions:
                score -= 25
            length = (rec.get("length") or 0) / 1000
            if duration and length:
                diff = abs(length - duration)
                if diff > 10:
                    score -= 40
                elif diff > 4:
                    score -= 15
            if album and tags.get("album") and _ratio(album, tags["album"]) > 0.8:
                score += 5
            releases = rec.get("releases") or []
            studio = _is_studio(_pick_release(releases))
            year = int((rec.get("first-release-date") or "9999")[:4] or 9999)
            credits = rec.get("artist-credit") or [{}]
            match = Match(max(0, min(100, score)), tags, rec.get("id", ""), release_id,
                          artist_id=(credits[0].get("artist") or {}).get("id", ""))
            ranked[match.recording_id] = (match, studio, len(releases), year)
        best = max(ranked.values(), key=lambda r: (r[0].confidence, r[1]), default=None)
        if best and best[1] and best[0].confidence >= 90:
            break  # good studio-album match already; skip the second request

    order = sorted(ranked.values(), key=lambda r: (-r[0].confidence, not r[1], -r[2], r[3]))
    matches = [r[0] for r in order]
    if not artist:
        # A title alone matches every cover version - never auto-apply that.
        for m in matches:
            m.confidence = min(m.confidence, 70)
    elif matches:
        # Search hits are often reissues; use the original album, year and track.
        _use_studio_album(matches[0], duration)
    return matches


@lru_cache(maxsize=256)
def studio_tracks(artist_id: str) -> dict:
    """``{normalized title: [track info, ...]}`` across an artist's studio albums.

    Uses MusicBrainz browse requests (one per album, cached), which - unlike
    search - reliably return an artist's original albums.
    """
    data = web.get_json(f"{MB}/release-group",
                        {"artist": artist_id, "type": "album", "limit": 100, "fmt": "json"})
    groups = [g for g in (data or {}).get("release-groups", []) if not g.get("secondary-types")]
    groups.sort(key=lambda g: g.get("first-release-date") or "9999")
    index: dict[str, list] = {}
    for g in groups[:40]:
        rels = web.get_json(f"{MB}/release", {"release-group": g["id"], "inc": "recordings",
                                              "status": "official", "limit": 10, "fmt": "json"})
        rels = (rels or {}).get("releases", [])
        # Prefer a CD/digital edition so track numbers are 1, 2, 3… not vinyl "B4".
        rels.sort(key=lambda r: not any((m.get("format") or "") in ("CD", "Digital Media")
                                        for m in r.get("media") or []))
        for rel in rels[:1]:
            for medium in rel.get("media") or []:
                for t in medium.get("tracks") or []:
                    index.setdefault(normalize(t.get("title", "")), []).append({
                        "album": g.get("title", ""),
                        "date": (g.get("first-release-date") or "")[:4],
                        "tracknumber": str(t.get("position") or t.get("number", "")),
                        "length": (t.get("length") or 0) / 1000,
                        "release_id": rel.get("id", ""),
                        "recording_id": (t.get("recording") or {}).get("id", ""),
                    })
    return index


def _use_studio_album(match: Match, duration: float) -> None:
    """Point ``match`` at the original studio album if the artist has one with it."""
    if not match.artist_id or match.confidence < 70:
        return
    entries = studio_tracks(match.artist_id).get(normalize(match.tags.get("title", "")), [])
    if duration:
        entries = [e for e in entries if not e["length"] or abs(e["length"] - duration) <= 10]
    if not entries:
        return
    e = entries[0]  # earliest album
    match.tags.update({k: e[k] for k in ("album", "date", "tracknumber") if e[k]})
    match.tags["albumartist"] = match.tags.get("artist", "")
    match.release_id, match.recording_id = e["release_id"], e["recording_id"] or match.recording_id


def search_acoustid(path: Path, api_key: str) -> list[Match]:
    """Identify a song purely by its sound - works even with no tags at all."""
    from .fingerprint import compressed_fingerprint

    fp = compressed_fingerprint(path) if api_key else None
    if not fp:
        return []
    data = web.get_json("https://api.acoustid.org/v2/lookup", {
        "client": api_key, "duration": int(fp[0]), "fingerprint": fp[1],
        "meta": "recordings releases releasegroups",
    })
    matches = []
    for result in (data or {}).get("results", []):
        for rec in result.get("recordings") or []:
            if not rec.get("title"):
                continue
            tags = {"title": rec["title"], "artist": _artist_credit(rec.get("artists"))}
            release_id = ""
            groups = rec.get("releasegroups") or []
            albums = [g for g in groups if g.get("type") == "Album"] or groups
            if albums:
                tags["album"] = albums[0].get("title", "")
                rels = albums[0].get("releases") or []
                if rels:
                    release_id = rels[0].get("id", "")
            matches.append(Match(int(result.get("score", 0) * 100), tags, rec.get("id", ""),
                                 release_id, "AcoustID"))
    matches.sort(key=lambda m: -m.confidence)
    return matches[:8]


def fetch_cover(release_id: str) -> Optional[bytes]:
    if not release_id:
        return None
    r = web.get(f"https://coverartarchive.org/release/{release_id}/front-500", timeout=30)
    if r is None or not r.content.startswith((b"\xff\xd8", b"\x89PNG")):
        return None
    return r.content


def fetch_lyrics(artist: str, title: str, album: str = "", duration: float = 0) -> str:
    """Plain lyrics from LRCLIB ('' when unknown or instrumental)."""
    if not (artist and title):
        return ""
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = int(round(duration))
    data = web.get_json("https://lrclib.net/api/get", params)
    if not data:
        hits = web.get_json("https://lrclib.net/api/search",
                            {"artist_name": artist, "track_name": title}) or []
        hits = [h for h in hits if h.get("plainLyrics")]
        if duration:
            hits.sort(key=lambda h: abs((h.get("duration") or 0) - duration))
        data = hits[0] if hits else None
    if not data or data.get("instrumental"):
        return ""
    return (data.get("plainLyrics") or "").strip()


@dataclass
class Proposal:
    """Suggested new tags for one file, waiting to be applied (or reviewed)."""

    path: Path
    current: dict
    duration: float = 0
    matches: list[Match] = field(default_factory=list)
    chosen: int = 0  # index into matches
    lyrics: str = ""
    apply: bool = False
    error: str = ""
    done: bool = False
    edited_lyrics: Optional[str] = None  # set when the user edits lyrics by hand

    @property
    def match(self) -> Optional[Match]:
        return self.matches[self.chosen] if self.matches else None

    @property
    def confidence(self) -> int:
        return self.match.confidence if self.match else 0

    def proposed(self) -> dict:
        """Current tags updated with the chosen match (and lyrics)."""
        out = dict(self.current)
        if self.match:
            out.update(self.match.tags)
        if self.edited_lyrics is not None:
            out["lyrics"] = self.edited_lyrics
        elif self.lyrics and not out.get("lyrics"):
            out["lyrics"] = self.lyrics
        return out
