import os
from pathlib import Path

from dupesort.core.duplicates import choose_keepers, merge_groups
from dupesort.core.hashing import PARTIAL_BYTES, find_exact_duplicates
from dupesort.core.history import Session, load_sessions, safe_filename
from dupesort.core.organize import plan_date_moves
from dupesort.core.scanner import DUPLICATES_DIR, scan
from dupesort.core.similar import group_similar


def write(p: Path, data: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_scan_filters_category_hidden_and_duplicates_folder(tmp_path):
    write(tmp_path / "a.mp3", b"x" * 10)
    write(tmp_path / "b.jpg", b"x" * 10)
    write(tmp_path / ".hidden.mp3", b"x" * 10)
    write(tmp_path / DUPLICATES_DIR / "old.mp3", b"x" * 10)
    write(tmp_path / "sub" / "c.FLAC", b"x" * 10)
    found = scan([tmp_path, tmp_path / "sub"], "music")  # overlapping roots
    assert sorted(f.path.name for f in found) == ["a.mp3", "c.FLAC"]


def test_exact_duplicates_need_identical_content(tmp_path):
    big = os.urandom(PARTIAL_BYTES * 3)
    middle_changed = big[:PARTIAL_BYTES + 5] + b"!" + big[PARTIAL_BYTES + 6:]
    write(tmp_path / "1.txt", big)
    write(tmp_path / "2.txt", big)
    write(tmp_path / "3.txt", middle_changed)  # same size, same head and tail
    write(tmp_path / "4.txt", b"small")
    write(tmp_path / "5.txt", b"small")
    write(tmp_path / "6.txt", b"other")
    groups = find_exact_duplicates(scan([tmp_path], "documents"))
    names = sorted(sorted(f.path.name for f in g) for g in groups)
    assert names == [["1.txt", "2.txt"], ["4.txt", "5.txt"]]


def test_merge_groups_joins_overlaps(tmp_path):
    files = [write(tmp_path / f"{i}.txt", str(i).encode()) for i in range(4)]
    entries = scan([tmp_path], "documents")
    by = {e.path.name: e for e in entries}
    groups = merge_groups([
        ("Identical file", [[by["0.txt"], by["1.txt"]]]),
        ("Same text", [[by["1.txt"], by["2.txt"]]]),
    ])
    assert len(groups) == 1
    assert sorted(f.path.name for f in groups[0].files) == ["0.txt", "1.txt", "2.txt"]
    assert groups[0].reason == "Identical file + Same text"


def test_choose_keepers_quality_and_preferred_folder(tmp_path):
    write(tmp_path / "a" / "x.txt", b"1")
    write(tmp_path / "b" / "x.txt", b"1")
    entries = scan([tmp_path], "documents")
    for e in entries:
        e.info["q"] = 1 if e.path.parent.name == "b" else 0
    groups = merge_groups([("Identical file", [entries])])
    choose_keepers(groups, "best", lambda f: (f.info["q"],))
    assert groups[0].files[next(iter(groups[0].keep))].path.parent.name == "b"
    choose_keepers(groups, "best", lambda f: (f.info["q"],), preferred_folder=tmp_path / "a")
    assert groups[0].files[next(iter(groups[0].keep))].path.parent.name == "a"


def test_move_duplicate_and_undo(tmp_path):
    write(tmp_path / "Album" / "song.mp3", b"abc")
    write(tmp_path / "song.mp3", b"abc")
    entry = next(e for e in scan([tmp_path], "music") if e.path.parent.name == "Album")
    session = Session("test")
    dst = session.move_duplicate(entry)
    assert dst == tmp_path / DUPLICATES_DIR / "Album" / "song.mp3"
    assert dst.exists() and not entry.path.exists()

    renamed = session.rename(tmp_path / "song.mp3", "Artist - Title.mp3")
    assert renamed.name == "Artist - Title.mp3"

    reloaded = load_sessions()[0]
    assert len(reloaded.ops) == 2
    assert reloaded.undo() == []
    assert (tmp_path / "Album" / "song.mp3").exists()
    assert (tmp_path / "song.mp3").exists()
    assert not (tmp_path / DUPLICATES_DIR).exists()  # emptied folders removed
    assert load_sessions()[0].undone


def test_rename_collision_and_case_only(tmp_path):
    a = write(tmp_path / "a.mp3", b"1")
    write(tmp_path / "B.mp3", b"2")
    s = Session("t")
    assert s.rename(a, "B.mp3").name == "B (1).mp3"
    c = write(tmp_path / "song.mp3", b"3")
    assert s.rename(c, "Song.mp3").name == "Song.mp3"
    assert (tmp_path / "Song.mp3").read_bytes() == b"3"


def test_safe_filename():
    assert safe_filename('AC/DC - What: "Now"?.mp3') == "AC_DC - What_ _Now__.mp3"
    assert safe_filename("CON.mp3") == "_CON.mp3"
    assert safe_filename("name. ") == "name"


def test_group_similar_hamming():
    items = [(0b0000, "a"), (0b0001, "b"), (0b0011, "c"), (0b1111_0000_0000, "d")]
    assert group_similar(items, 1) == [["a", "b", "c"]]  # chained a-b-c
    assert group_similar(items, 0) == []


def test_plan_date_moves(tmp_path):
    from datetime import datetime

    write(tmp_path / "p.jpg", b"1")
    write(tmp_path / "2021" / "03" / "q.jpg", b"2")
    entries = scan([tmp_path], "photos")
    for e in entries:
        e.info["date"] = datetime(2021, 3, 9)
    moves = plan_date_moves(entries, "{year}/{month:02d}")
    assert [(f.path.name, t) for f, t in moves] == [("p.jpg", tmp_path / "2021" / "03" / "p.jpg")]


def test_date_from_name():
    from datetime import datetime

    from dupesort.core.organize import date_from_name

    assert date_from_name("VID-20230815-WA0003.mp4") == datetime(2023, 8, 15)
    assert date_from_name("IMG_20190704_123000.jpg") == datetime(2019, 7, 4)
    assert date_from_name("2021-12-31 party.mov") == datetime(2021, 12, 31)
    assert date_from_name("IMG_0815.MOV") is None
    assert date_from_name("20231345.jpg") is None


def test_keeper_prefers_original_over_copy_name(tmp_path):
    write(tmp_path / "backup" / "IMG_1 copy.jpg", b"same")
    write(tmp_path / "IMG_1.jpg", b"same")
    write(tmp_path / "IMG_1 (2).jpg", b"same")
    groups = merge_groups([("Identical file", [scan([tmp_path], "photos")])])
    choose_keepers(groups, "best")
    assert groups[0].files[next(iter(groups[0].keep))].path.name == "IMG_1.jpg"


def test_capitalize_names(tmp_path):
    from dupesort.core.history import Session
    from dupesort.core.organize import apply_moves, capitalize, plan_capitalize
    from dupesort.core.scanner import scan

    assert capitalize("kansas - dust in the wind") == "Kansas - Dust In The Wind"
    assert capitalize("03 - don't stop me now (live at wembley)") == \
        "03 - Don't Stop Me Now (Live At Wembley)"
    assert capitalize("ac/dc - back in black") == "Ac/Dc - Back In Black"
    assert capitalize("my iPod's 3rd mix_final") == "My IPod's 3rd Mix_Final"
    assert capitalize("été à paris") == "Été À Paris"
    assert capitalize("DUST IN THE WIND", "words_lower") == "Dust In The Wind"
    assert capitalize("McCartney - mull of kintyre", "words") == "McCartney - Mull Of Kintyre"
    assert capitalize("dust in the wind", "first") == "Dust in the wind"
    assert capitalize("2024-05-06 beach", "first") == "2024-05-06 Beach"
    assert capitalize("") == "" and capitalize("123") == "123"

    lib = tmp_path / "lib"
    lib.mkdir()
    for name in ("kansas - dust in the wind.MP3", "Already Fine.mp3", "queen - bohemian rhapsody.mp3"):
        (lib / name).write_bytes(b"x" * 10)
    plan = plan_capitalize(scan([lib], "music"))
    assert sorted(t.name for _, t in plan) == ["Kansas - Dust In The Wind.MP3",
                                               "Queen - Bohemian Rhapsody.mp3"]
    session = Session("Capitalized names")
    assert apply_moves(plan, session) == []
    assert sorted(p.name for p in lib.iterdir()) == [
        "Already Fine.mp3", "Kansas - Dust In The Wind.MP3", "Queen - Bohemian Rhapsody.mp3"]
    assert session.undo() == []
    assert sorted(p.name for p in lib.iterdir()) == [
        "Already Fine.mp3", "kansas - dust in the wind.MP3", "queen - bohemian rhapsody.mp3"]
