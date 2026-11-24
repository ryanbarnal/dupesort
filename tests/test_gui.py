import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_intro_frames_render(app):
    from PySide6.QtGui import QImage, QPainter

    from dupesort.gui.intro import paint_intro

    for t in (0.0, 0.3, 0.45, 0.7, 1.0):
        img = QImage(320, 200, QImage.Format_ARGB32)
        p = QPainter(img)
        paint_intro(p, 320, 200, t)
        p.end()
    # Mid-animation the thin white rings are drawn on the near-black background.
    img = QImage(320, 200, QImage.Format_ARGB32)
    p = QPainter(img)
    paint_intro(p, 320, 200, 0.5)
    p.end()
    assert img.pixelColor(5, 5).lightness() < 20
    row = [img.pixelColor(x, 100).lightness() for x in range(320)]
    assert max(row[:160]) > 200 and max(row[160:]) > 200


def test_themes_and_main_window(app):
    from PySide6.QtGui import QPalette

    from dupesort.gui.main_window import GUIDE, MainWindow

    w = MainWindow()
    names = [w.nav.item(i).text() for i in range(w.nav.count())]
    assert names == ["Music", "Photos", "Videos", "Documents", "History", "Help & Support"]
    w.set_theme(mode="Dark", accent="Pink")
    assert app.palette().color(QPalette.Window).lightness() < 60
    assert app.palette().color(QPalette.Highlight).name() == "#ec4899"
    w.set_theme(mode="Light")
    assert app.palette().color(QPalette.Window).lightness() > 200
    assert w.settings.accent == "Pink" and w.settings.theme_mode == "Light"
    w.set_theme(accent="Mono")  # the default: black-and-white
    assert app.palette().color(QPalette.Highlight).name() == "#111111"
    assert GUIDE.is_file() and "Ryan Ocbina Barnal" in GUIDE.read_text(encoding="utf-8")
    tabs = [w.pages[i][2].tabs.tabText(j) for i in range(4)
            for j in range(w.pages[i][2].tabs.count())]
    for expected in ("Convert", "Convert && resize", "PDF tools"):
        assert expected in tabs


def test_support_mail_has_version(app):
    from dupesort import SUPPORT_EMAIL, __version__
    from dupesort.gui.support_page import support_mail_url

    url = support_mail_url().toString()
    assert url.startswith(f"mailto:{SUPPORT_EMAIL}") and __version__ in url


def test_tags_table_status_column_fits_window(app):
    from pathlib import Path

    from dupesort.gui.main_window import MainWindow
    from dupesort.music.lookup import Match, Proposal

    w = MainWindow()
    w.show()
    page = w.pages[0][2]
    page.tabs.setCurrentWidget(page.tag_tab)
    tab = page.tag_tab
    tab._add_proposal(Proposal(Path("a very long file name for this song.mp3"), {"title": "x"}, 1, [
        Match(70, {"artist": "An Artist With A Long Name", "title": "A Long Song Title",
                   "album": "A Long Album Name", "genre": "Alternative Rock"})]))
    tab._add_proposal(Proposal(Path("b.mp3"), {}, 1, [], error="No match found online"))
    app.processEvents()
    h = tab.table.horizontalHeader()
    last = tab.table.columnCount() - 1
    assert h.sectionViewportPosition(last) + h.sectionSize(last) <= tab.table.viewport().width()
    assert not tab.table.horizontalScrollBar().isVisible()
    w.grab()
    w.close()


def test_every_icon_draws(app):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QPushButton

    from dupesort.gui import icons, theme

    theme.apply("Light", "Mono")
    for kind in icons.KINDS:
        assert not icons.make(kind, QColor("#111")).pixmap(24, 24).isNull()
    btn = QPushButton("Scan")
    btn.setDefault(True)
    icons.attach(btn, "scan")
    theme.apply("Dark", "Mono")  # redraws attached button icons without errors
    assert not btn.icon().isNull()


def test_page_layout_folders_and_update_bar(app, monkeypatch):
    from dupesort import updates
    from dupesort.gui.main_window import MainWindow

    w = MainWindow()
    page = w.pages[0][2]
    page.folders.add_folder("/a/Music")
    page.folders.add_folder("/b/Music")
    page.folders.add_folder("/b/Music")  # already there
    expected = [os.path.normpath("/a/Music"), os.path.normpath("/b/Music")]  # \\ on Windows
    assert page.folders.folders() == expected
    assert w.settings.folders["music"] == expected
    # Scan is the page's main button only while Duplicates is showing.
    assert page.scan_btn.isDefault()
    page.switch.setCurrentIndex(2)
    assert page.tabs.currentIndex() == 2 and not page.scan_btn.isDefault()

    opened = []
    monkeypatch.setattr("dupesort.gui.update_bar.QDesktopServices.openUrl",
                        lambda url: opened.append(url.toString()))
    w.update_bar.offer(updates.Release("9.0.0", "https://example.com/rel", "", {}))
    assert not w.update_bar.isHidden() and "9.0.0" in w.update_bar.text.text()
    w.update_bar.install_btn.click()  # from source: opens the release page
    assert opened == ["https://example.com/rel"]
    w.update_bar.skip_btn.click()
    assert w.update_bar.isHidden() and w.settings.skipped_update == "9.0.0"


def test_music_preview_player(app, tmp_path):
    from conftest import make_wav

    from dupesort.core.scanner import scan
    from dupesort.gui.main_window import MainWindow

    make_wav(tmp_path / "a.wav", seconds=1.0)
    page = MainWindow().pages[0][2]
    player = page.preview.player
    assert player is not None and not player.isEnabled()
    entry = scan([tmp_path], "music")[0]
    page.preview.show_entry(entry)
    assert player.isEnabled() and player.path == entry.path
    player.play()  # no sound device here; it must not crash either way
    for _ in range(20):
        app.processEvents()
    player.toggle()
    page.preview.show_entry(None)
    assert not player.isEnabled()
    # Videos get a player with a picture area; photos and documents get none.
    w = MainWindow()
    assert w.pages[1][2].preview.player is None
    video = w.pages[2][2].preview.player
    try:  # some Linux setups lack the system libraries Qt's video widget needs
        import PySide6.QtMultimediaWidgets  # noqa: F401
        has_video = True
    except ImportError:
        has_video = False
    # Without them the player still works for sound; it just shows no picture.
    assert video is not None and (video.video is not None) == has_video
    assert w.pages[3][2].preview.player is None


def test_document_previews(app, tmp_path):
    from PIL import Image

    from dupesort.core.scanner import FileEntry
    from dupesort.gui.main_window import MainWindow
    from dupesort.gui.widgets import document_preview

    pdf = tmp_path / "letter.pdf"
    Image.new("RGB", (600, 800), "white").save(pdf)
    txt = tmp_path / "notes.txt"
    txt.write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"PK\x03\x04 not really a docx")

    kind, img = document_preview(pdf)
    assert kind == "image" and img.width == 320
    kind, text = document_preview(txt)
    assert kind == "text" and text.splitlines()[0] == "line 0" and len(text.splitlines()) == 40
    assert document_preview(docx) is None

    preview = MainWindow().pages[3][2].preview
    entry = lambda p: FileEntry(p, p.stat().st_size, p.stat().st_mtime, tmp_path)
    preview.show_entry(entry(pdf))
    assert not preview.image.pixmap().isNull() and preview.excerpt.isHidden()
    preview.show_entry(entry(txt))
    assert "line 39" in preview.excerpt.text() and not preview.excerpt.isHidden()
    preview.show_entry(entry(docx))
    assert "No preview" in preview.image.text()


def _open_files():
    import os

    fd_dir = "/proc/self/fd"
    out = set()
    for fd in os.listdir(fd_dir):
        try:
            out.add(os.path.realpath(os.readlink(os.path.join(fd_dir, fd))))
        except OSError:
            pass
    return out


def test_player_lets_go_of_the_file(app, tmp_path):
    """Windows can't change a file that is open, so the preview must close it before
    tags are written, files renamed or moved (it reopens it on the next play)."""
    import os
    import sys
    import time

    import pytest
    from conftest import make_wav

    from dupesort.core.scanner import scan
    from dupesort.gui.main_window import MainWindow
    from dupesort.gui.player import release_all

    path = os.path.realpath(make_wav(tmp_path / "song.wav", seconds=2.0))
    window = MainWindow()  # keep a reference, or the window goes away mid-test
    page = window.pages[0][2]
    player = page.preview.player
    page.preview.show_entry(scan([tmp_path], "music")[0])
    # Selecting a song doesn't open it.
    assert player._player is None or player._player.source().isEmpty()
    player.play()
    end = time.time() + 3
    while time.time() < end and sys.platform.startswith("linux") and path not in _open_files():
        app.processEvents()
    if sys.platform.startswith("linux") and path not in _open_files():
        pytest.skip("the media backend didn't open the file here (no audio support)")
    release_all()
    for _ in range(50):
        app.processEvents()
    assert player._player.source().isEmpty()
    if sys.platform.startswith("linux"):
        assert path not in _open_files()
    # Play again: the file is reopened.
    player.play()
    assert not player._player.source().isEmpty()
    # Starting any job (tag writing, renaming, moving…) releases it too.
    page.run_task("Test", lambda t: None, lambda _r: None)
    assert player._player.source().isEmpty()
    end = time.time() + 5
    while page.task is not None and time.time() < end:  # let the job finish before teardown
        app.processEvents()
    assert page.task is None
    window.close()


def test_reopens_where_you_left_off(app, tmp_path, monkeypatch):
    from conftest import make_wav
    from PySide6.QtWidgets import QMessageBox

    from dupesort.core.duplicates import DuplicateGroup
    from dupesort.core.scanner import scan
    from dupesort.gui.main_window import MainWindow
    from dupesort.music.lookup import Match, Proposal

    for d in ("A", "B"):
        make_wav(tmp_path / "lib" / d / "song.wav")
    files = scan([tmp_path / "lib"], "music")

    w = MainWindow()
    page = w.pages[0][2]
    page.files = files
    page.groups = [DuplicateGroup(list(files), "Identical file", {1})]
    page.tree.set_groups(page.groups)
    page.tag_tab.restore_state([Proposal(files[0].path, {"title": "x"}, 1.0,
                                         [Match(70, {"title": "Song"})], apply=True)])
    convert = page.tabs.widget(2)
    convert.files.add([files[0].path])
    page.tabs.setCurrentIndex(1)
    w.nav.setCurrentRow(0)
    # A lookup is still running when the window closes.
    page.task = type("FakeTask", (), {"cancel": lambda self: None})()
    page._task_label = "Looking up songs online…"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)  # "Stop it and quit?"
    assert w.close()
    page.task = None

    w2 = MainWindow()
    p2 = w2.pages[0][2]
    assert w2.nav.currentRow() == 0 and p2.tabs.currentIndex() == 1
    assert len(p2.groups) == 1 and p2.groups[0].keep == {1}
    assert p2.tree.topLevelItemCount() == 1
    assert len(p2.tag_tab.proposals) == 1 and p2.tag_tab.table.rowCount() == 1
    assert p2.tag_tab.proposals[0].apply
    assert p2.tabs.widget(2).files.paths() == [files[0].path]
    assert "closed during" in p2.status.text() and "Looking up songs online" in p2.status.text()
    # Other pages had nothing to restore.
    assert w2.pages[1][2].groups == []

    # Turned off in Settings: start fresh.
    w2.settings.restore_session = False
    w2.settings.save()
    assert MainWindow().pages[0][2].groups == []
