"""The activation window, and the check run before anything that changes files."""

from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .. import APP_NAME, BUY_URL, SUPPORT_EMAIL, licensing
from . import icons


def buy_url() -> QUrl:
    if BUY_URL:
        return QUrl(BUY_URL)
    subject = quote(f"{APP_NAME} license")
    body = quote(f"Hello,\n\nI'd like to buy a {APP_NAME} license.\n\nName for the license: \n")
    return QUrl(f"mailto:{SUPPORT_EMAIL}?subject={subject}&body={body}")


class ActivateDialog(QDialog):
    """Shows the trial or license status and takes a license key."""

    def __init__(self, reason: str = "", parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Activate {APP_NAME}")
        self.setMinimumWidth(480)
        st = licensing.status()
        self.title = QLabel(objectName="heading")
        self.text = QLabel(wordWrap=True)
        self.text.setTextFormat(Qt.RichText)
        self.key = QPlainTextEdit()
        self.key.setPlaceholderText("Paste your license key here (DUPESORT-…)")
        self.key.setFixedHeight(84)
        self.message = QLabel(wordWrap=True, objectName="muted")
        self.activate_btn = QPushButton("Activate")
        self.activate_btn.setDefault(True)
        icons.attach(self.activate_btn, "check")  # after setDefault: drawn in the button's colour
        self.activate_btn.clicked.connect(self._activate)
        buy = icons.attach(QPushButton("Get a license"), "mail")
        buy.clicked.connect(lambda: QDesktopServices.openUrl(buy_url()))
        close = QPushButton("Not now" if not st.licensed else "Close")
        close.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(buy)
        row.addStretch()
        row.addWidget(close)
        row.addWidget(self.activate_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.text)
        lay.addWidget(self.key)
        lay.addWidget(self.message)
        lay.addLayout(row)
        self._show(st, reason)

    def _show(self, st: licensing.Status, reason: str = "") -> None:
        if st.licensed:
            self.title.setText(f"{APP_NAME} is activated")
            self.text.setText(f"Licensed to <b>{st.licensed.name}</b>. Thank you for supporting "
                              f"{APP_NAME}!")
            self.key.setVisible(False)
            self.activate_btn.setVisible(False)
            return
        if st.days_left > 0:
            self.title.setText(st.summary())
            self.text.setText(
                f"Everything in {APP_NAME} works during the {licensing.TRIAL_DAYS}-day trial. "
                "After that you can still scan and look at the results, but moving, tagging, "
                "renaming, organizing and converting need a license. Enter your key to activate "
                "now.")
        else:
            self.title.setText("Your free trial has ended")
            self.text.setText(
                (f"To {reason}, please activate {APP_NAME}. " if reason else
                 f"To change files again, please activate {APP_NAME}. ") +
                "Scanning, results, previews and <b>Undo</b> in History keep working.<br><br>"
                "<b>Get a license</b> to buy one; your key arrives by email.")

    def _activate(self) -> None:
        ok, text = licensing.activate(self.key.toPlainText())
        self.message.setText(text)
        if ok:
            self._show(licensing.status())
            self.activate_btn.setVisible(False)


def require(parent: QWidget, reason: str) -> bool:
    """True if files may be changed now; otherwise asks for activation first.
    ``reason`` completes "To …", e.g. "move duplicates"."""
    if licensing.status().can_change_files:
        return True
    ActivateDialog(reason, parent).exec()
    ok = licensing.status().can_change_files
    win = parent.window() if parent else None
    if ok and hasattr(win, "refresh_license"):
        win.refresh_license()
    return ok
