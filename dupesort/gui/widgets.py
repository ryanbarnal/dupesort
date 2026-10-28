"""Reusable widgets: folder picker, duplicate-group tree and file preview."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QListWidget, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.duplicates import DuplicateGroup
from ..core.scanner import FileEntry


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def describe(f: FileEntry) -> str:
    """Short quality summary shown next to each file."""
    i, bits = f.info, []
    if i.get("width"):
        bits.append(f"{i['width']}×{i['height']}")
    if i.get("bitrate"):
        bits.append(f"{i['bitrate'] // 1000} kbps")
    if i.get("lossless"):
        bits.append("lossless")
    if i.get("duration"):
        m, s = divmod(int(i["duration"]), 60)
        bits.append(f"{m}:{s:02d}")
    tags = i.get("tags") or {}
    if tags.get("artist") or tags.get("title"):
        bits.append(f"{tags.get('artist', '?')} – {tags.get('title', '?')}")
    if i.get("date"):
        bits.append(i["date"].strftime("%Y-%m-%d"))
    return "  ·  ".join(bits)


def reveal(path: Path) -> None:
    """Show ``path`` in Explorer / Finder / the Linux file manager."""
    import subprocess
    import sys

    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class FolderList(QWidget):
    changed = Signal()

    def __init__(self, folders: list[str], parent=None) -> None:
        super().__init__(parent)
        self.list = QListWidget()
        self.list.addItems(folders)
        self.list.setMaximumHeight(90)
        add, remove = QPushButton("Add folder…"), QPushButton("Remove")
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        buttons = QVBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.list, 1)
        lay.addLayout(buttons)

    def folders(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def _add(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder to scan")
        if d and d not in self.folders():
            self.list.addItem(os.path.normpath(d))
            self.changed.emit()

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self.changed.emit()


class DuplicateTree(QTreeWidget):
    """Groups as parent rows; tick the files to KEEP (at least one per group)."""

    selected_file = Signal(object)  # FileEntry or None
    keep_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Keep / File", "Folder", "Size", "Details", "Modified"])
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        h = self.header()
        h.setSectionResizeMode(0, QHeaderView.Interactive)
        h.resizeSection(0, 300)
        h.resizeSection(1, 280)
        self.groups: list[DuplicateGroup] = []
        self._updating = False
        self.itemChanged.connect(self._on_changed)
        self.currentItemChanged.connect(self._on_current)

    def set_groups(self, groups: list[DuplicateGroup]) -> None:
        self._updating = True
        self.clear()
        self.groups = groups
        for gi, g in enumerate(groups):
            top = QTreeWidgetItem([f"Group {gi + 1}: {len(g.files)} files", "",
                                   human_size(g.wasted_bytes), g.reason, ""])
            top.setData(0, Qt.UserRole, (gi, -1))
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            for fi, f in enumerate(g.files):
                child = QTreeWidgetItem([
                    f.path.name, str(f.path.parent), human_size(f.size), describe(f),
                    datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d %H:%M"),
                ])
                child.setToolTip(0, str(f.path))
                child.setData(0, Qt.UserRole, (gi, fi))
                child.setCheckState(0, Qt.Checked if fi in g.keep else Qt.Unchecked)
                top.addChild(child)
            self.addTopLevelItem(top)
            top.setExpanded(gi < 200)
        self._updating = False

    def _on_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return
        gi, fi = item.data(0, Qt.UserRole)
        if fi < 0:
            return
        g = self.groups[gi]
        if item.checkState(0) == Qt.Checked:
            g.keep.add(fi)
        else:
            g.keep.discard(fi)
            if not g.keep:  # never allow a group with nothing kept
                self._updating = True
                item.setCheckState(0, Qt.Checked)
                g.keep.add(fi)
                self._updating = False
        top = item.parent()
        top.setText(2, human_size(g.wasted_bytes))
        self.keep_changed.emit()

    def _on_current(self, item: Optional[QTreeWidgetItem], _prev) -> None:
        if item is None:
            self.selected_file.emit(None)
            return
        gi, fi = item.data(0, Qt.UserRole)
        self.selected_file.emit(self.groups[gi].files[fi] if fi >= 0 else None)


class Preview(QWidget):
    def __init__(self, show_images: bool, parent=None) -> None:
        super().__init__(parent)
        self.show_images = show_images
        self.entry: Optional[FileEntry] = None
        self.image = QLabel(alignment=Qt.AlignCenter)
        self.image.setMinimumSize(240, 200 if show_images else 0)
        self.image.setVisible(show_images)
        self.text = QLabel(wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        self.text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        open_btn, show_btn = QPushButton("Open"), QPushButton("Show in folder")
        open_btn.clicked.connect(lambda: self.entry and QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.entry.path))))
        show_btn.clicked.connect(lambda: self.entry and reveal(self.entry.path))
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addWidget(show_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(self.image)
        lay.addWidget(self.text, 1)
        lay.addLayout(row)
        self.setMinimumWidth(260)

    def show_entry(self, entry: Optional[FileEntry]) -> None:
        self.entry = entry
        if entry is None:
            self.text.setText("Select a file to preview it.")
            self.image.clear()
            return
        lines = [f"<b>{entry.path.name}</b>", str(entry.path.parent), human_size(entry.size)]
        d = describe(entry)
        if d:
            lines.append(d.replace("  ·  ", "<br>"))
        tags = entry.info.get("tags") or {}
        for k in ("album", "genre", "date"):
            if tags.get(k):
                lines.append(f"{k.title()}: {tags[k]}")
        if tags.get("lyrics"):
            lines.append("Lyrics: embedded")
        self.text.setText("<br>".join(lines))
        if self.show_images:
            from ..photos import thumbnail

            img = thumbnail(entry.path)
            if img is None:
                self.image.setText("(no preview)")
            else:
                data = img.tobytes("raw", "RGB")
                qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
                self.image.setPixmap(QPixmap.fromImage(qimg.copy()))
