"""Main window: a sidebar for Music / Photos / Videos / Documents / History / Help."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QDesktopServices, QGuiApplication, QKeySequence, QPalette,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import APP_NAME, AUTHOR, __version__, licensing, videos
from ..music import fingerprint
from ..core import state
from ..settings import Settings
from . import icons, theme
from .category_page import DocumentPage, MusicPage, PhotoPage, VideoPage
from .history_page import HistoryPage
from .settings_dialog import SettingsDialog
from .support_page import SupportPage, logo_pixmap
from .update_bar import UpdateBar

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
        # Trial / license status; opens the activation window.
        self.trial_btn = QPushButton(objectName="trial")
        self.trial_btn.setCursor(Qt.PointingHandCursor)
        self.trial_btn.clicked.connect(self.open_activation)
        sl.addWidget(self.trial_btn)
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

        self.update_bar = UpdateBar(self.settings)
        self.update_bar.quit_requested.connect(self._quit_for_update)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.update_bar)
        lay = QHBoxLayout()
        outer.addLayout(lay, 1)
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
        self.refresh_license()
        self._restore_session()

        # Look for a new version shortly after start-up, then every 6 hours.
        self.update_timer = QTimer(self, interval=6 * 60 * 60 * 1000)
        self.update_timer.timeout.connect(self._auto_check_updates)
        QTimer.singleShot(8000, self._auto_check_updates)
        self.update_timer.start()

    # --- remembering where you left off ----------------------------------------
    def _restore_session(self) -> None:
        if not self.settings.restore_session:
            return
        win = state.load_window()
        if win.get("size"):
            self.resize(*win["size"])
        if win.get("maximized"):
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
        for _, _, page in self.pages:
            if hasattr(page, "restore_state"):
                page.restore_state()
        if 0 <= win.get("page", 0) < self.nav.count():
            self.nav.setCurrentRow(win.get("page", 0))

    def _save_session(self, interrupted: dict) -> None:
        if not self.settings.restore_session:
            return
        for _, _, page in self.pages:
            if hasattr(page, "save_state"):
                page.save_state(interrupted.get(id(page), ""))
        size = self.normalGeometry().size() if self.isMaximized() else self.size()
        try:
            state.save_window({"page": self.nav.currentRow(), "maximized": self.isMaximized(),
                               "size": [size.width(), size.height()]})
        except OSError:
            pass

    # --- trial and license --------------------------------------------------------
    def refresh_license(self) -> None:
        st = licensing.status()
        self.trial_btn.setVisible(st.licensed is None)
        if st.licensed is None:
            self.trial_btn.setText(f"{st.summary()} · Activate" if st.days_left <= 0 else
                                   st.summary())
            self.trial_btn.setProperty("ended", st.days_left <= 0)
            self.trial_btn.style().unpolish(self.trial_btn)
            self.trial_btn.style().polish(self.trial_btn)
            self.trial_btn.setToolTip("Enter a license key, or see what the trial includes")

    def open_activation(self) -> None:
        from .license_dialog import ActivateDialog

        ActivateDialog(parent=self).exec()
        self.refresh_license()

    def _auto_check_updates(self) -> None:
        if os.environ.get("DUPESORT_NO_UPDATE_CHECK"):  # set by the tests
            return
        if self.settings.check_updates and not self.update_bar.isVisible():
            self.update_bar.check(manual=False)

    def _quit_for_update(self) -> None:
        if self.close():
            QApplication.instance().quit()

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
        activate = QAction(f"Activate {APP_NAME}…", self)
        activate.triggered.connect(self.open_activation)
        check = QAction("Check for updates…", self)
        check.setMenuRole(QAction.ApplicationSpecificRole)
        check.triggered.connect(lambda: self.update_bar.check(manual=True))
        support = QAction("Help && Support", self)
        support.triggered.connect(lambda: self.nav.setCurrentRow(len(self.pages) - 1))
        about = QAction(f"About {APP_NAME}", self)
        about.setMenuRole(QAction.AboutRole)
        about.triggered.connect(self.about)
        for a in (guide, support, check, activate):
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
                    f"<p>Created by <b>{AUTHOR}</b>.</p><p>{licensing.status().summary()}.</p>")
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
        # Remember the work (and what was still running) before stopping it.
        self._save_session({id(p): getattr(p, "_task_label", "") for p in busy})
        for p in busy:
            p.task.cancel()
        self.settings.save()
        event.accept()
