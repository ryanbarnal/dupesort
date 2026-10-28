"""Main window: a sidebar for Music / Photos / Videos / Documents / History."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget,
    QStyle, QWidget,
)

from .. import APP_NAME, __version__, videos
from ..music import fingerprint
from ..settings import Settings
from .category_page import DocumentPage, MusicPage, PhotoPage, VideoPage
from .history_page import HistoryPage
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.settings = Settings.load()

        self.nav = QListWidget()
        self.nav.setFixedWidth(170)
        self.nav.setIconSize(QSize(22, 22))
        self.stack = QStackedWidget()
        style = self.style()
        self.pages = [
            ("Music", QStyle.SP_MediaPlay, MusicPage("music", "Music", self.settings)),
            ("Photos", QStyle.SP_DesktopIcon, PhotoPage("photos", "Photos", self.settings)),
            ("Videos", QStyle.SP_MediaSeekForward, VideoPage("videos", "Videos", self.settings)),
            ("Documents", QStyle.SP_FileIcon,
             DocumentPage("documents", "Documents", self.settings)),
        ]
        self.history = HistoryPage()
        self.pages.append(("History", QStyle.SP_BrowserReload, self.history))
        for name, icon, page in self.pages:
            item = QListWidgetItem(style.standardIcon(icon), name)
            item.setSizeHint(QSize(0, 40))
            self.nav.addItem(item)
            self.stack.addWidget(page)
            if hasattr(page, "history_changed"):
                page.history_changed.connect(self.history.refresh)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.addWidget(self.nav)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

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
        help_menu = menu.addMenu("&Help")
        about = QAction(f"About {APP_NAME}", self)
        about.setMenuRole(QAction.AboutRole)
        about.triggered.connect(self.about)
        help_menu.addAction(about)
        self.statusBar().showMessage("Ready")

    def open_settings(self) -> None:
        if SettingsDialog(self.settings, self).exec():
            self.statusBar().showMessage("Settings saved", 3000)

    def about(self) -> None:
        def state(ok: bool) -> str:
            return "found" if ok else "not installed (optional)"

        QMessageBox.about(self, APP_NAME, (
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Finds duplicate music, photos, videos and documents, moves them into a "
            "<i>_Duplicates</i> folder and organizes the rest. Every change can be undone.</p>"
            f"<p>Chromaprint (fpcalc): {state(fingerprint.available())}<br>"
            f"FFmpeg: {state(videos.ffmpeg_available())}</p>"
            "<p>Song data: MusicBrainz, AcoustID, Cover Art Archive. Lyrics: LRCLIB. "
            "Movies/TV: TMDb (this product uses the TMDb API but is not endorsed or "
            "certified by TMDb).</p>"))

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
