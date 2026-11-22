"""History of every change, with one-click undo."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.history import history_dir, load_sessions
from . import icons


class HistoryPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.sessions = []
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When", "What", "Changes", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        undo = QPushButton("Undo selected")
        icons.attach(undo, "undo")
        undo.clicked.connect(self.undo)
        folder = QPushButton("Open history folder")
        icons.attach(folder, "folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(history_dir()))))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(folder)
        row.addWidget(undo)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("History", objectName="heading"))
        lay.addWidget(QLabel("Every move, rename and tag change is recorded "
                             "here. Undo puts files back where they were and restores the "
                             "previous tags."))
        lay.addWidget(self.table, 1)
        lay.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        self.sessions = load_sessions()
        self.table.setRowCount(len(self.sessions))
        for r, s in enumerate(self.sessions):
            cells = [datetime.fromtimestamp(s.created).strftime("%Y-%m-%d %H:%M"), s.title,
                     str(len(s.ops)), "Undone" if s.undone else ""]
            for c, text in enumerate(cells):
                self.table.setItem(r, c, QTableWidgetItem(text))

    def undo(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        chosen = [self.sessions[r] for r in rows if not self.sessions[r].undone]
        if not chosen:
            return
        names = "\n".join(f"• {s.title}" for s in chosen)
        if QMessageBox.question(self, "Undo", f"Undo these changes?\n\n{names}\n\n"
                                "Rescan afterwards to refresh the results.") != QMessageBox.Yes:
            return
        problems = []
        for s in chosen:  # newest first, as listed
            problems += s.undo()
        self.refresh()
        if problems:
            QMessageBox.warning(self, "Undo finished with problems", "\n".join(problems[:30]))
        else:
            QMessageBox.information(self, "Undo", "Done.")
