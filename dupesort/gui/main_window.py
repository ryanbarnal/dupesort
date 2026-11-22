"""Main window: a sidebar for Music / Photos / Videos / Documents / History / Help."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QDesktopServices, QGuiApplication, QKeySequence, QPalette,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import APP_NAME, AUTHOR, __version__, videos
from ..music import fingerprint
from ..settings import Settings
from . import icons, theme
from .category_page import DocumentPage, MusicPage, PhotoPage, VideoPage
from .history_page import HistoryPage
from .settings_dialog import SettingsDialog
from .support_page import SupportPage, logo_pixmap

GUIDE = Path(__file__).resolve().parent / "guide.html"


class GuideWindow(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} User Guide")
        self.resize(860, 760)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setSource(QUrl.fromLocalFile(str(GUIDE)))
        browser_btn = QPushButton("Open in web browser")
        icons.attach(browser_btn, "open")
        browser_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(GUIDE))))
        close = QPushButton("Close")
        icons.attach(close, "close")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(browser_btn)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.browser, 1)
        lay.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 840)
        self.settings = Settings.load()
        self.guide = None
        theme.apply(self.settings.theme_mode, self.settings.accent)
        try:  # follow the OS when it switches between light and dark
            QGuiApplication.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
        except AttributeError:
            pass

        # Sidebar: logo + name, then the section list.
        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.logo = logo = QLabel()
        name = QVBoxLayout()
        name.setSpacing(0)
        name.addWidget(QLabel(APP_NAME, objectName="brand"))
        name.addWidget(QLabel(f"v{__version__}", objectName="version"))
        brand.addWidget(logo)
        brand.addLayout(name, 1)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(18, 18))
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WA_StyledBackground, True)
        sidebar.setFixedWidth(200)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 16, 12, 12)
        sl.addLayout(brand)
        sl.addSpacing(18)
        sl.addWidget(self.nav, 1)
        sl.addWidget(QLabel(f"by {AUTHOR}", objectName="credit", wordWrap=True))

        self.stack = QStackedWidget()
        self.pages = [
            ("Music", "music", MusicPage("music", "Music", self.settings)),
            ("Photos", "photos", PhotoPage("photos", "Photos", self.settings)),
            ("Videos", "videos", VideoPage("videos", "Videos", self.settings)),
            ("Documents", "documents", DocumentPage("documents", "Documents", self.settings)),
        ]
        self.history = HistoryPage()
        self.support = SupportPage(self.open_guide)
        self.pages.append(("History", "history", self.history))
        self.pages.append(("Help & Support", "help", self.support))
        for name, icon, page in self.pages:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, icon)
            item.setSizeHint(QSize(0, 34))
            self.nav.addItem(item)
            self.stack.addWidget(page)
            if hasattr(page, "history_changed"):
                page.history_changed.connect(self.history.refresh)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(sidebar)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 14, 20, 10)
        bl.addWidget(self.stack)
        lay.addWidget(body, 1)
        self.setCentralWidget(central)
        self._build_menus()
        self._refresh_icons()
        self.statusBar().showMessage("Ready")

    def _refresh_icons(self) -> None:
        self.logo.setPixmap(logo_pixmap(28))
        self.support.logo.setPixmap(logo_pixmap(96))
        muted = QColor(theme.current.get("muted", "#6e6e6b"))
        text = self.palette().color(QPalette.WindowText)
        for i in range(self.nav.count()):
            item = self.nav.item(i)
            item.setIcon(icons.make(item.data(Qt.UserRole), muted, selected=text))

    # --- menus ------------------------------------------------------------------
    def _build_menus(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        prefs = QAction("Settings…", self)
        prefs.setMenuRole(QAction.PreferencesRole)
        prefs.setShortcut(QKeySequence.Preferences)
        prefs.triggered.connect(self.open_settings)
        quit_ = QAction("Quit", self)
        quit_.setMenuRole(QAction.QuitRole)
        quit_.setShortcut(QKeySequence.Quit)
        quit_.triggered.connect(self.close)
        file_menu.addAction(prefs)
        file_menu.addSeparator()
        file_menu.addAction(quit_)

        view = menu.addMenu("&View")
        appearance = view.addMenu("Appearance")
        self.mode_actions = QActionGroup(self)
        for mode in theme.MODES:
            a = QAction(mode if mode != "System" else "Match system", self, checkable=True)
            a.setData(mode)
            a.setChecked(mode == self.settings.theme_mode)
            a.triggered.connect(lambda _=False, m=mode: self.set_theme(mode=m))
            self.mode_actions.addAction(a)
            appearance.addAction(a)
        accent_menu = view.addMenu("Accent colour")
        self.accent_actions = QActionGroup(self)
        for name in theme.ACCENTS:
            a = QAction(name, self, checkable=True)
            a.setChecked(name == self.settings.accent)
            a.triggered.connect(lambda _=False, n=name: self.set_theme(accent=n))
            self.accent_actions.addAction(a)
            accent_menu.addAction(a)
        view.addSeparator()
        self.intro_action = QAction("Play intro at start-up", self, checkable=True)
        self.intro_action.setChecked(self.settings.play_intro)
        self.intro_action.toggled.connect(self._set_intro)
        view.addAction(self.intro_action)
        replay = QAction("Play intro now", self)
        replay.triggered.connect(self.play_intro)
        view.addAction(replay)

        help_menu = menu.addMenu("&Help")
        guide = QAction(f"{APP_NAME} User Guide", self)
        guide.setShortcut(QKeySequence.HelpContents)
        guide.triggered.connect(self.open_guide)
        support = QAction("Help && Support", self)
        support.triggered.connect(lambda: self.nav.setCurrentRow(len(self.pages) - 1))
        about = QAction(f"About {APP_NAME}", self)
        about.setMenuRole(QAction.AboutRole)
        about.triggered.connect(self.about)
        for a in (guide, support):
            help_menu.addAction(a)
        help_menu.addSeparator()
        help_menu.addAction(about)

    # --- actions ----------------------------------------------------------------
    def set_theme(self, mode: str = None, accent: str = None) -> None:
        if mode:
            self.settings.theme_mode = mode
        if accent:
            self.settings.accent = accent
        self.settings.save()
        theme.apply(self.settings.theme_mode, self.settings.accent)
        self._refresh_icons()
        for a in self.mode_actions.actions():
            a.setChecked(a.data() == self.settings.theme_mode)
        for a in self.accent_actions.actions():
            a.setChecked(a.text() == self.settings.accent)

    def _system_theme_changed(self, *_):
        if self.settings.theme_mode == "System":
            theme.apply("System", self.settings.accent)
            self._refresh_icons()

    def _set_intro(self, on: bool) -> None:
        self.settings.play_intro = on
        self.settings.save()

    def play_intro(self) -> None:
        from .intro import IntroWindow

        self._intro = IntroWindow()
        self._intro.start()

    def open_guide(self) -> None:
        if self.guide is None:
            self.guide = GuideWindow(self)
        self.guide.show()
        self.guide.raise_()
        self.guide.activateWindow()

    def open_settings(self) -> None:
        if SettingsDialog(self.settings, self).exec():
            self.set_theme()
            self.intro_action.setChecked(self.settings.play_intro)
            self.statusBar().showMessage("Settings saved", 3000)

    def about(self) -> None:
        def state(ok: bool) -> str:
            return "found" if ok else "not installed (optional)"

        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setIconPixmap(logo_pixmap(96))
        box.setText(f"<h3>{APP_NAME} {__version__}</h3>"
                    f"<p>Created by <b>{AUTHOR}</b>.</p>")
        box.setInformativeText(
            "Finds duplicate music, photos, videos and documents, organizes and converts "
            "them. Every change can be undone.<br><br>"
            f"Chromaprint (fpcalc): {state(fingerprint.available())}<br>"
            f"FFmpeg: {state(videos.ffmpeg_available())}<br><br>"
            "Credits for the open-source projects used are on the Help &amp; Support page.")
        box.exec()

    def closeEvent(self, event) -> None:
        busy = [p for _, _, p in self.pages if getattr(p, "task", None) is not None]
        if busy and QMessageBox.question(
                self, "Still working", "A job is still running. Stop it and quit?") \
                != QMessageBox.Yes:
            event.ignore()
            return
        for p in busy:
            p.task.cancel()
        self.settings.save()
        event.accept()
