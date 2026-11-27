"""Reusable widgets: folder picker, duplicate-group tree and file preview."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.duplicates import DuplicateGroup
from ..core.scanner import FileEntry
from . import icons


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


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps them onto new lines, like text."""

    def __init__(self, parent=None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, move=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, move: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        gap = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + gap, 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + gap
            line = max(line, hint.height())
        return y + line - rect.y()


class FolderList(QWidget):
    """The folders to scan, as chips. Each chip has a remove (×) button."""

    changed = Signal()

    def __init__(self, folders: list[str], parent=None) -> None:
        super().__init__(parent)
        self._folders: list[str] = []
        self.flow = FlowLayout(self)
        self.add_btn = icons.attach(QPushButton("Add folder…"), "folder-plus")
        self.add_btn.setObjectName("chipAdd")
        self.add_btn.clicked.connect(self._add)
        self.flow.addWidget(self.add_btn)
        for f in folders:
            self.add_folder(f, notify=False)

    def folders(self) -> list[str]:
        return list(self._folders)

    def add_folder(self, path: str, notify: bool = True) -> None:
        path = os.path.normpath(path)
        if path in self._folders:
            return
        self._folders.append(path)
        chip = QPushButton()
        chip.setObjectName("chip")
        chip.setProperty("folder", path)
        chip.setToolTip(f"{path}\nClick to remove")
        icons.attach(chip, "close", 12)
        chip.setLayoutDirection(Qt.RightToLeft)  # × after the name
        chip.clicked.connect(lambda _=False, p=path, c=chip: self._remove(p, c))
        # Keep "Add folder" last.
        self.flow.takeAt(self.flow.count() - 1)
        self.flow.addWidget(chip)
        self.flow.addWidget(self.add_btn)
        self._relabel()
        if notify:
            self.changed.emit()

    def _relabel(self) -> None:
        """Show each folder's name, plus its parent where two names are the same."""
        names = [Path(f).name or f for f in self._folders]
        for i in range(self.flow.count()):
            chip = self.flow.itemAt(i).widget()
            path = chip.property("folder") if chip else None
            if path:
                name = Path(path).name or path
                if names.count(name) > 1 and Path(path).parent.name:
                    name = f"{Path(path).parent.name} › {name}"
                chip.setText(name)

    def _add(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder to scan")
        if d:
            self.add_folder(d)

    def _remove(self, path: str, chip: QPushButton) -> None:
        self._folders.remove(path)
        self.flow.removeWidget(chip)
        chip.deleteLater()
        self._relabel()
        self.changed.emit()


SORT_ROLE = Qt.UserRole + 1


class SortItem(QTreeWidgetItem):
    """A row that sorts by the value it stores (bytes, a date), not by the text shown, so
    "9.5 MB" comes after "800 KB"."""

    def __lt__(self, other) -> bool:
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a, b = self.data(col, SORT_ROLE), other.data(col, SORT_ROLE)
        if a is not None and b is not None:
            return a < b
        return self.text(col).lower() < other.text(col).lower()


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
        # Click a column heading to sort (again to reverse). Groups stay together: groups
        # sort among themselves and the files in each group sort the same way.
        h.setSectionsClickable(True)
        h.setSortIndicatorShown(True)
        self.setToolTip("Click a column heading to sort by it; click again to reverse.")
        self.itemChanged.connect(self._on_changed)
        self.currentItemChanged.connect(self._on_current)

    def set_groups(self, groups: list[DuplicateGroup]) -> None:
        self._updating = True
        column, order = self.sortColumn(), self.header().sortIndicatorOrder()
        if not self.groups and not groups or not self.isSortingEnabled():
            column, order = 2, Qt.DescendingOrder  # first time: most space to free first
        self.setSortingEnabled(False)  # fill first, then sort once
        self.clear()
        self.groups = groups
        for gi, g in enumerate(groups):
            top = SortItem([f"Group {gi + 1}: {len(g.files)} files", "",
                            human_size(g.wasted_bytes), g.reason, ""])
            top.setData(0, Qt.UserRole, (gi, -1))
            # A group sorts by its first file's name and folder, the space it frees, its
            # reason and its newest file.
            first = min(g.files, key=lambda f: f.path.name.lower())
            top.setData(0, SORT_ROLE, first.path.name.lower())
            top.setData(1, SORT_ROLE, str(first.path.parent).lower())
            top.setData(2, SORT_ROLE, g.wasted_bytes)
            top.setData(3, SORT_ROLE, g.reason.lower())
            top.setData(4, SORT_ROLE, max(f.mtime for f in g.files))
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            for fi, f in enumerate(g.files):
                child = SortItem([
                    f.path.name, str(f.path.parent), human_size(f.size), describe(f),
                    datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d %H:%M"),
                ])
                child.setToolTip(0, str(f.path))
                child.setData(0, Qt.UserRole, (gi, fi))
                child.setData(0, SORT_ROLE, f.path.name.lower())
                child.setData(1, SORT_ROLE, str(f.path.parent).lower())
                child.setData(2, SORT_ROLE, f.size)
                child.setData(3, SORT_ROLE, describe(f).lower())
                child.setData(4, SORT_ROLE, f.mtime)
                child.setCheckState(0, Qt.Checked if fi in g.keep else Qt.Unchecked)
                top.addChild(child)
            self.addTopLevelItem(top)
            top.setExpanded(gi < 200)
        self.setSortingEnabled(True)
        self.sortByColumn(column, order)
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
        top.setData(2, SORT_ROLE, g.wasted_bytes)
        self.keep_changed.emit()

    def _on_current(self, item: Optional[QTreeWidgetItem], _prev) -> None:
        if item is None:
            self.selected_file.emit(None)
            return
        gi, fi = item.data(0, Qt.UserRole)
        self.selected_file.emit(self.groups[gi].files[fi] if fi >= 0 else None)


TEXT_PREVIEW = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm", ".rtf"}


def document_preview(path: Path, width: int = 320):
    """("image", PIL image) for the first page of a PDF, ("text", str) for the start of a text
    file, or None for formats that need their own app (Word, Excel…)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            import pypdfium2 as pdfium

            doc = pdfium.PdfDocument(str(path))
            try:
                page = doc[0]
                scale = width / max(1.0, page.get_width())
                return "image", page.render(scale=scale).to_pil().convert("RGB")
            finally:
                doc.close()
        except Exception:
            return None
    if ext in TEXT_PREVIEW:
        try:
            with open(path, "rb") as fh:
                raw = fh.read(4000)
            text = raw.decode("utf-8", errors="replace")
            return "text", "\n".join(text.splitlines()[:40])
        except OSError:
            return None
    return None


class Preview(QWidget):
    """Details of the selected file, with a preview where one makes sense: a photo, the first
    page of a PDF or lines of a text file, or a player for music and videos."""

    HINTS = {"music": "Select a song to see its details and play it.",
             "videos": "Select a video to see its details and play it."}

    def __init__(self, kind: str = "", parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.show_images = kind in ("photos", "documents")
        self.player = None
        if kind in ("music", "videos"):
            from .player import MiniPlayer

            self.player = MiniPlayer(video=kind == "videos")
        self.entry: Optional[FileEntry] = None
        self.image = QLabel(alignment=Qt.AlignCenter)
        self.image.setMinimumSize(240, 200 if self.show_images else 0)
        self.image.setVisible(self.show_images)
        self.excerpt = QLabel(wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse,
                              objectName="excerpt")
        self.excerpt.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.excerpt.setVisible(False)
        self.text = QLabel(wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        self.text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        open_btn, show_btn = QPushButton("Open"), QPushButton("Show in folder")
        icons.attach(open_btn, "open")
        icons.attach(show_btn, "folder")
        open_btn.clicked.connect(lambda: self.entry and QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.entry.path))))
        show_btn.clicked.connect(lambda: self.entry and reveal(self.entry.path))
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addWidget(show_btn)
        lay = QVBoxLayout(self)
        if self.player and self.player.video:
            lay.addWidget(self.player.video)
        lay.addWidget(self.image)
        lay.addWidget(self.excerpt)
        lay.addWidget(self.text, 1)
        if self.player:
            lay.addWidget(self.player)
        lay.addLayout(row)
        self.setMinimumWidth(260)

    def hideEvent(self, event) -> None:
        if self.player:  # stop and close the file when you switch section or page
            self.player.release()
        super().hideEvent(event)

    def _set_image(self, img) -> None:
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
        self.image.setPixmap(QPixmap.fromImage(qimg.copy()))

    def show_entry(self, entry: Optional[FileEntry]) -> None:
        self.entry = entry
        if self.player:
            self.player.load(entry.path if entry else None)
        self.excerpt.setVisible(False)
        if entry is None:
            self.text.setText(self.HINTS.get(self.kind, "Select a file to preview it."))
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
        if self.kind == "photos":
            from ..photos import thumbnail

            img = thumbnail(entry.path)
            if img is None:
                self.image.setText("(no preview)")
            else:
                self._set_image(img)
        elif self.kind == "documents":
            found = document_preview(entry.path)
            self.image.setVisible(bool(found and found[0] == "image"))
            self.image.clear()
            if found and found[0] == "image":
                self._set_image(found[1])
            elif found:
                self.excerpt.setText(found[1])
                self.excerpt.setVisible(True)
            else:
                self.image.setVisible(True)
                self.image.setText("No preview for this kind of file.\nUse Open to view it.")
