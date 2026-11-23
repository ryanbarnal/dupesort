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
    assert page.folders.folders() == ["/a/Music", "/b/Music"]
    assert w.settings.folders["music"] == ["/a/Music", "/b/Music"]
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
