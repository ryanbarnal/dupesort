"""Help & Support page: user guide, contact support, donate, credits."""

from __future__ import annotations

import platform
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, AUTHOR, DONATE_URL, SUPPORT_EMAIL, __version__

LOGO = Path(__file__).resolve().parent / "logo.png"

CREDITS = [
    ("Qt for Python (PySide6)", "user interface", "LGPL"),
    ("Mutagen", "music tags", "GPL"),
    ("Pillow & ImageHash", "photos and visual matching", "MIT-CMU / BSD"),
    ("FFmpeg", "audio & video conversion", "LGPL / GPL"),
    ("Chromaprint / AcoustID", "matching songs by sound", "LGPL / MIT"),
    ("MusicBrainz & Cover Art Archive", "song details and album art", "CC0"),
    ("LRCLIB", "lyrics", "free service"),
    ("TMDb", "movie & TV names (not endorsed or certified by TMDb)", "API terms"),
    ("Real-ESRGAN", "AI photo upscaling", "BSD-3"),
    ("pypdf & PDFium", "PDF tools", "BSD / Apache-2.0"),
]


def logo_pixmap(size: int) -> QPixmap:
    pm = QPixmap(str(LOGO))
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull() \
        else pm


def support_mail_url() -> QUrl:
    body = (f"\n\n\n---\n{APP_NAME} {__version__}\n"
            f"{platform.system()} {platform.release()} ({platform.machine()})\n")
    return QUrl(f"mailto:{SUPPORT_EMAIL}?subject={quote(f'{APP_NAME} support')}"
                f"&body={quote(body)}")


class SupportPage(QWidget):
    def __init__(self, open_guide, parent=None) -> None:
        super().__init__(parent)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(96))
        title = QLabel(f"<h1 style='margin:0'>{APP_NAME}</h1>"
                       f"<div>Version {__version__}</div>"
                       f"<div style='margin-top:6px'>Created by <b>{AUTHOR}</b></div>")
        head = QHBoxLayout()
        head.addWidget(logo)
        head.addSpacing(12)
        head.addWidget(title, 1)

        guide = QPushButton("Open the User Guide")
        guide.setDefault(True)
        guide.clicked.connect(open_guide)
        mail = QPushButton("Contact support by email")
        mail.clicked.connect(lambda: QDesktopServices.openUrl(support_mail_url()))
        help_box = QGroupBox("Get help")
        hl = QVBoxLayout(help_box)
        hl.addWidget(QLabel("Most questions are answered in the User Guide. Still stuck, or "
                            "found a bug? Email support - your DupeSort version and system "
                            "are filled in for you.", wordWrap=True))
        row = QHBoxLayout()
        row.addWidget(guide)
        row.addWidget(mail)
        row.addStretch()
        hl.addLayout(row)
        hl.addWidget(QLabel(f"<small>{SUPPORT_EMAIL}</small>",
                            textInteractionFlags=Qt.TextSelectableByMouse))

        boxes = [help_box]
        if DONATE_URL:
            donate = QPushButton("♥  Donate")
            donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATE_URL)))
            d_box = QGroupBox("Support development")
            dl = QVBoxLayout(d_box)
            dl.addWidget(QLabel(f"{APP_NAME} is free. If it saved you time or disk space, "
                                "you can support its development with a donation.",
                                wordWrap=True))
            dl.addWidget(donate, 0, Qt.AlignLeft)
            boxes.append(d_box)

        credits = QGroupBox("Credits")
        grid = QGridLayout(credits)
        grid.addWidget(QLabel(f"<b>{APP_NAME}</b> - designed and created by "
                              f"<b>{AUTHOR}</b>."), 0, 0, 1, 3)
        grid.addWidget(QLabel("Built with these open-source projects and free services:"),
                       1, 0, 1, 3)
        for r, (name, what, lic) in enumerate(CREDITS, 2):
            grid.addWidget(QLabel(f"<b>{name}</b>"), r, 0)
            grid.addWidget(QLabel(what), r, 1)
            grid.addWidget(QLabel(f"<small>{lic}</small>"), r, 2)
        grid.setColumnStretch(3, 1)  # keep the three columns compact
        grid.setHorizontalSpacing(24)
        boxes.append(credits)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.addLayout(head)
        for b in boxes:
            lay.addWidget(b)
        lay.addWidget(QLabel(f"<small>© {AUTHOR}. Song data © MusicBrainz contributors."
                             "</small>"))
        lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
