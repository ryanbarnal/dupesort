from pathlib import Path

from conftest import make_wav

from dupesort import web
from dupesort.core.history import Session, load_sessions
from dupesort.core.scanner import scan
from dupesort.music import lookup, organizer
from dupesort.music.fingerprint import similarity
from dupesort.music.tags import format_name, guess_from_filename, read_tags, write_tags
from dupesort.settings import Settings


def test_write_read_tags_with_lyrics_and_cover(tmp_path):
    p = make_wav(tmp_path / "x.wav")
    write_tags(p, {"title": "Song", "artist": "Band", "genre": "Rock",
                   "tracknumber": "3", "lyrics": "la la la"},
               cover=b"\xff\xd8\xff\xe0fakejpeg")
    t = read_tags(p)
    assert t == {"title": "Song", "artist": "Band", "genre": "Rock",
                 "tracknumber": "3", "lyrics": "la la la"}
    write_tags(p, {"title": "Only"}, clear_missing=True)
    assert read_tags(p) == {"title": "Only"}


def test_guess_from_filename():
    assert guess_from_filename(Path("03 - Daft Punk - One More Time.mp3")) == \
        {"artist": "Daft Punk", "title": "One More Time"}
    assert guess_from_filename(Path("Adele - Hello (Official Video).mp3")) == \
        {"artist": "Adele", "title": "Hello"}
    assert guess_from_filename(Path("track.mp3")) == {"title": "track"}


def test_format_name():
    tags = {"artist": "Queen", "title": "Bohemian Rhapsody", "lyrics": "..."}
    assert format_name("{artist} - {title}", tags, ".mp3") == "Queen - Bohemian Rhapsody.mp3"
    assert format_name("{artist} - {title}", {"title": "x"}, ".mp3") is None
    assert format_name("{nope", tags, ".mp3") is None


def test_normalize():
    assert lookup.normalize("Beyoncé feat. Jay-Z") == "beyonce"
    assert lookup.normalize("Song (Remastered 2011)") == "song"
    assert lookup.normalize("Simon & Garfunkel") == "simon and garfunkel"


def test_fingerprint_similarity():
    import random

    random.seed(1)
    a = [random.getrandbits(32) for _ in range(300)]
    noisy = [x ^ (1 << random.randrange(32)) for x in a]  # 1 bit of 32 flipped
    shifted = [random.getrandbits(32) for _ in range(10)] + a  # 10 frames of lead-in
    other = [random.getrandbits(32) for _ in range(300)]
    assert similarity(a, noisy) > 0.95
    assert similarity(a, shifted) > 0.99
    assert similarity(a, other) < 0.6


def test_same_tag_duplicates_respect_duration(tmp_path):
    for name, secs in (("a.wav", 2.0), ("b.wav", 2.5), ("c.wav", 6.0)):
        p = make_wav(tmp_path / name, seconds=secs)
        write_tags(p, {"artist": "Band", "title": "Song (Remastered)"})
    s = Settings(music_match_by_fingerprint=False)
    groups = organizer.find_duplicates(scan([tmp_path], "music"), s)
    assert [sorted(f.path.name for f in g.files) for g in groups] == [["a.wav", "b.wav"]]
    assert groups[0].reason == "Same artist & title"


MB_RESPONSE = {"recordings": [
    {"id": "rec-1", "score": 100, "title": "One More Time", "length": 1000,
     "artist-credit": [{"name": "Daft Punk", "joinphrase": ""}],
     "releases": [
         {"id": "rel-single", "title": "One More Time", "status": "Official", "date": "2000",
          "release-group": {"primary-type": "Single"}},
         {"id": "rel-album", "title": "Discovery", "status": "Official", "date": "2001-03-12",
          "release-group": {"primary-type": "Album"},
          "media": [{"track": [{"number": "1"}]}]},
     ]},
    {"id": "rec-2", "score": 80, "title": "One More Time (Live)", "length": 300000,
     "artist-credit": [{"name": "Daft Punk"}], "releases": []},
]}


def fake_get_json(url, params=None, **kw):
    if "musicbrainz.org/ws/2/recording/" in url:
        return {"genres": [{"name": "french house", "count": 5}]}
    if "musicbrainz.org/ws/2/recording" in url:
        return MB_RESPONSE
    if "lrclib.net/api/get" in url:
        assert params["artist_name"] == "Daft Punk"
        return {"plainLyrics": "One more time\nWe're gonna celebrate", "instrumental": False}
    return None


def test_build_and_apply_proposal(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "get_json", fake_get_json)
    p = make_wav(tmp_path / "01 - daft punk - one more time.wav")
    s = Settings(fetch_cover_art=False)
    prop = organizer.build_proposal(p, s)
    assert prop.confidence >= 90 and prop.apply
    new = prop.proposed()
    assert new["album"] == "Discovery" and new["date"] == "2001" and new["tracknumber"] == "1"
    assert new["genre"] == "French House"
    assert new["lyrics"].startswith("One more time")

    session = Session("tag")
    final = organizer.apply_proposal(prop, session, s, rename=True)
    assert final.name == "Daft Punk - One More Time.wav"
    assert read_tags(final)["artist"] == "Daft Punk"

    assert load_sessions()[0].undo() == []
    assert p.exists() and read_tags(p) == {}  # name and (empty) tags restored


def test_low_confidence_needs_review(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "get_json", fake_get_json)
    p = make_wav(tmp_path / "Somebody - Something Else.wav")
    prop = organizer.build_proposal(p, Settings())
    assert prop.match is not None and prop.confidence < 90 and not prop.apply


def test_live_acoustic_and_unplugged_versions_are_not_duplicates(tmp_path):
    from dupesort.music.organizer import version_of

    specs = {  # file: (tags, folder)
        "studio.wav": ({"artist": "Band", "title": "Song", "album": "Debut"}, "Debut"),
        "studio copy.wav": ({"artist": "Band", "title": "Song", "album": "Debut"}, "Copies"),
        "acoustic.wav": ({"artist": "Band", "title": "Song (Acoustic)"}, "Singles"),
        "unplugged.wav": ({"artist": "Band", "title": "Song", "album": "MTV Unplugged"}, "x"),
        "concert.wav": ({"artist": "Band", "title": "Song"}, "Live in Concert 2004"),
        "genre.wav": ({"artist": "Band", "title": "Song", "genre": "Live"}, "y"),
        "remaster.wav": ({"artist": "Band", "title": "Song (Remastered 2011)"}, "z"),
    }
    for name, (tags, folder) in specs.items():
        p = make_wav(tmp_path / folder / name, seconds=2.0)
        write_tags(p, tags)
    files = scan([tmp_path], "music")
    groups = organizer.find_duplicates(files, Settings(music_match_by_fingerprint=False))
    # The studio takes match each other, and so do the two live takes - but a live,
    # acoustic or unplugged take never matches the studio one.
    assert sorted(sorted(f.path.name for f in g.files) for g in groups) == \
        [["concert.wav", "genre.wav"], ["remaster.wav", "studio copy.wav", "studio.wav"]]

    # Turning the option off groups every take of the song together again.
    off = Settings(music_match_by_fingerprint=False, music_separate_versions=False)
    assert len(organizer.find_duplicates(scan([tmp_path], "music"), off)[0].files) == 7

    # "Live" in the song's own name is not a live recording.
    oasis = make_wav(tmp_path / "o" / "Oasis - Live Forever.wav")
    [entry] = [f for f in scan([tmp_path / "o"], "music")]
    entry.info["tags"] = {}
    assert version_of(entry) == frozenset() and oasis.exists()
