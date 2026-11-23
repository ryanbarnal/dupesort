"""A thin bar at the top of the window that offers a new version and installs it."""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
)

from .. import APP_NAME, __version__, updates
from ..settings import Settings
from . import icons
from .worker import Task


class UpdateBar(QFrame):
    """Hidden until a newer release is found. "Install" downloads it, then:
    Windows installs and restarts; macOS/Linux open the download to drag into place."""

    quit_requested = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBar")
        self.settings = settings
        self.release: Optional[updates.Release] = None
        self.task: Optional[Task] = None
        self._checking = False

        self.text = QLabel()
        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.setVisible(False)
        self.notes_btn = icons.attach(QPushButton("What's new"), "book")
        self.install_btn = icons.attach(QPushButton("Install update"), "check")
        self.later_btn = QPushButton("Later")
        self.skip_btn = QPushButton("Skip this version")
        self.notes_btn.clicked.connect(self._open_page)
        self._on_install = self._install  # becomes "show the download" once downloaded
        self.install_btn.clicked.connect(lambda: self._on_install())
        self.later_btn.clicked.connect(self._later)
        self.skip_btn.clicked.connect(self._skip)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.progress)
        for b in (self.notes_btn, self.skip_btn, self.later_btn, self.install_btn):
            lay.addWidget(b)
        self.hide()

    # --- checking ------------------------------------------------------------
    def check(self, manual: bool = False) -> None:
        """Look for a new version in the background. ``manual`` reports every outcome."""
        if self._checking or self.task is not None:
            return
        self._checking = True
        task = Task(lambda t: updates.latest_release())

        def done(rel):
            self._checking = False
            if rel is None:
                if manual:
                    QMessageBox.information(
                        self.window(), "Check for updates",
                        "Couldn't reach GitHub to check for updates. Check your internet "
                        "connection and try again.")
                return
            if not updates.is_newer(rel.version):
                if manual:
                    QMessageBox.information(self.window(), "Check for updates",
                                            f"You have the latest version of {APP_NAME} "
                                            f"({__version__}).")
                return
            if manual or rel.version != self.settings.skipped_update:
                self.offer(rel)

        def failed(_tb):
            self._checking = False
            if manual:
                QMessageBox.information(self.window(), "Check for updates",
                                        "Couldn't check for updates right now.")

        task.signals.finished.connect(done)
        task.signals.failed.connect(failed)
        task.start()

    def offer(self, rel: updates.Release) -> None:
        self.release = rel
        self.text.setText(f"<b>{APP_NAME} {rel.version}</b> is available "
                          f"<span style='opacity:.7'>(you have {__version__})</span>")
        self.install_btn.setText("Install update" if self._installs_itself() else "Download")
        self._on_install = self._install
        self.install_btn.setDefault(True)
        icons.attach(self.install_btn, "check")
        self._set_busy(False)
        self.show()

    # --- actions -------------------------------------------------------------
    def _installs_itself(self) -> bool:
        return updates.can_install_itself() and self.release and self.release.installer()

    def _open_page(self) -> None:
        QDesktopServices.openUrl(QUrl(self.release.page if self.release else
                                      updates.RELEASES_PAGE))

    def _later(self) -> None:
        if self.task is not None:
            self.task.cancel()
        self.hide()

    def _skip(self) -> None:
        if self.release:
            self.settings.skipped_update = self.release.version
            self.settings.save()
        self.hide()

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        for b in (self.install_btn, self.skip_btn, self.notes_btn):
            b.setEnabled(not busy)
        self.later_btn.setText("Cancel" if busy else "Later")

    def _install(self) -> None:
        rel = self.release
        asset = rel.installer() if rel else None
        # Running from source, or no download for this system: show the release page.
        if not rel or not asset or not getattr(sys, "frozen", False):
            self._open_page()
            return
        name, url = asset
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.text.setText(f"Downloading {APP_NAME} {rel.version}…")

        def job(t: Task):
            return updates.download(url, name, lambda d, n: t.progress(d, n), t.cancelled)

        def on_progress(done: int, total: int, _text: str) -> None:
            if total:
                self.progress.setRange(0, total)
                self.progress.setValue(done)

        def finished(path):
            self.task = None
            if path is None:  # cancelled
                self.offer(rel)
                self.hide()
                return
            self.progress.setVisible(False)
            if updates.install(path):
                self.text.setText(f"Installing {APP_NAME} {rel.version}… it will open again "
                                  "in a moment.")
                self.quit_requested.emit()
                return
            self._set_busy(False)
            self.progress.setVisible(False)
            how = ("Open the disk image and drag DupeSort into Applications, replacing the "
                   "old copy." if sys.platform == "darwin" else
                   "Extract the archive over your current DupeSort folder.")
            self.text.setText(f"<b>{APP_NAME} {rel.version}</b> is downloaded. {how}")
            self.install_btn.setText("Show download")
            self._on_install = lambda: updates.install(path)

        def failed(tb: str):
            self.task = None
            self._set_busy(False)
            self.text.setText("The download didn't finish. Try again, or get it from the "
                              "release page (What's new).")

        task = Task(job)
        task.signals.progress.connect(on_progress)
        task.signals.finished.connect(finished)
        task.signals.failed.connect(failed)
        self.task = task.start()

