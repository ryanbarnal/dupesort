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
    # Mid-animation the circles are visible: centre-left pixel is sky blue-ish.
    img = QImage(320, 200, QImage.Format_ARGB32)
    p = QPainter(img)
    paint_intro(p, 320, 200, 0.5)
    p.end()
    c = img.pixelColor(110, 100)
    assert c.blue() > 150 and c.red() < 150


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
