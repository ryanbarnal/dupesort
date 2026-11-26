"""Work is remembered between runs, and stale files are left out when it comes back."""

import os
import time
from datetime import datetime
from pathlib import Path

from conftest import make_wav

from dupesort.core import state
from dupesort.core.duplicates import DuplicateGroup
from dupesort.core.scanner import scan
from dupesort.music.lookup import Match, Proposal


def _library(tmp_path):
    a = make_wav(tmp_path / "A" / "song.wav")
    b = make_wav(tmp_path / "B" / "song.wav")
    c = make_wav(tmp_path / "C" / "song.wav")
    files = scan([tmp_path], "music")
    for f in files:
        f.info.update({"date": datetime(2024, 5, 6, 7, 8, 9), "phash": 2**63 + 5,
                       "tags": {"title": "Song", "lyrics": "la " * 1000}, "frames": [1, 2]})
    by = {f.path: f for f in files}
    return files, [by[a], by[b], by[c]]


def test_page_round_trip(tmp_path):
    files, (a, b, c) = _library(tmp_path)
    group = DuplicateGroup([a, b, c], "Identical file", {2})
    prop = Proposal(a.path, {"title": "Song"}, 2.0, [Match(95, {"artist": "Band"}, "rec-1")],
                    apply=True, edited_lyrics="mine")
    state.save_page("music", files, [group], section=1, proposals=[prop],
                    convert={"AudioConvertTab": {"files": [str(a.path)]}})

    saved = state.load_page("music")
    assert saved["section"] == 1 and saved["dropped"] == 0 and not saved["interrupted"]
    [g] = saved["groups"]
    assert [f.path for f in g.files] == [a.path, b.path, c.path]
    assert g.keep == {2} and g.reason == "Identical file"
    info = g.files[0].info
    assert info["date"] == datetime(2024, 5, 6, 7, 8, 9) and info["phash"] == 2**63 + 5
    assert info["tags"]["lyrics"] == "(embedded)" and "frames" not in info
    [p] = saved["proposals"]
    assert p.path == a.path and p.apply and p.edited_lyrics == "mine"
    assert p.match.confidence == 95 and p.match.tags == {"artist": "Band"}
    assert saved["convert"]["AudioConvertTab"]["files"] == [str(a.path)]


def test_moved_or_changed_files_are_left_out(tmp_path):
    files, (a, b, c) = _library(tmp_path)
    state.save_page("music", files, [DuplicateGroup([a, b, c], "x", {2})])
    os.remove(c.path)  # the kept copy is gone
    saved = state.load_page("music")
    [g] = saved["groups"]
    assert [f.path for f in g.files] == [a.path, b.path] and g.keep == {0}
    assert saved["dropped"] == 1

    time.sleep(0.01)
    b.path.write_bytes(b"changed")  # now only one file is unchanged: no group left
    saved = state.load_page("music")
    assert saved["groups"] == [] and saved["dropped"] == 2


def test_broken_or_missing_state_is_ignored(tmp_path):
    assert state.load_page("photos") is None
    (state.state_dir() / "photos.json.gz").write_bytes(b"not gzip")
    assert state.load_page("photos") is None
    state.clear_page("photos")
    assert state.load_page("photos") is None


def test_keep_ticks_survive_any_file_order(tmp_path):
    """The ticked copy comes back on the right file even when the scan listed the files in
    a different order from the group (this differs between computers)."""
    files, (a, b, c) = _library(tmp_path)
    for order in ([c, b, a], [b, c, a], [a, c, b]):
        state.save_page("music", order, [DuplicateGroup([a, b, c], "x", {1})])
        [g] = state.load_page("music")["groups"]
        assert [g.files[i].path for i in g.keep] == [b.path]
    os.remove(a.path)  # the first copy goes: the tick stays on b
    state.save_page("music", [c, b, a], [DuplicateGroup([a, b, c], "x", {1})])
    [g] = state.load_page("music")["groups"]
    assert [f.path for f in g.files] == [b.path, c.path] and [g.files[i].path for i in g.keep] == [b.path]
