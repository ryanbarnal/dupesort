"""Optional organizing: date folders (photos/videos), TMDb names, document types."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import documents, videos
from ..core.history import Session
from . import icons
from ..core.organize import apply_moves, date_source, file_date, plan_date_moves


class PlanTab(QWidget):
    """Preview a list of planned moves/renames in a table, then apply the ticked ones."""

    columns = ["Apply", "File", "From", "To"]
    apply_label = "Apply ticked"
    apply_icon = "check"

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.settings = page, page.settings
        self.plan: list[tuple] = []  # (FileEntry, target Path, extra text)
        self.controls = QHBoxLayout()
        self.preview_btn = QPushButton("Preview changes")
        icons.attach(self.preview_btn, "eye")
        self.preview_btn.clicked.connect(self.preview)
        self.build_controls(self.controls)
        self.controls.addWidget(self.preview_btn)
        self.controls.addStretch()

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for col, w in enumerate((50, 220, 260)):
            self.table.horizontalHeader().resizeSection(col, w)

        self.summary = QLabel(self.hint())
        self.summary.setWordWrap(True)
        self.apply_btn = QPushButton(self.apply_label)
        icons.attach(self.apply_btn, self.apply_icon)
        self.apply_btn.clicked.connect(self.apply)
        page._busy_widgets += [self.preview_btn, self.apply_btn]
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.apply_btn)

        lay = QVBoxLayout(self)
        lay.addLayout(self.controls)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)

    # hooks
    def build_controls(self, row: QHBoxLayout) -> None:
        pass

    def hint(self) -> str:
        return "Scan first, then press Preview changes. Nothing changes until you apply."

    def read_controls(self) -> dict:
        """Read widget values on the UI thread before planning in the background."""
        return {}

    def make_plan(self, files, opts: dict) -> list[tuple]:
        raise NotImplementedError

    def session_title(self, n: int) -> str:
        return f"Organized {n} files"

    # shared flow
    def _candidates(self):
        """Scanned files, minus duplicates that are about to be moved away."""
        dupes = {id(f) for g in self.page.groups for f in g.duplicates}
        return [f for f in self.page.files if id(f) not in dupes]

    def preview(self) -> None:
        if not self.page.files:
            QMessageBox.information(self, "Scan first", "Scan the folders first.")
            return
        files, opts = self._candidates(), self.read_controls()
        self.page.run_task("Preparing preview…", lambda t: self.make_plan(files, opts),
                           self._show_plan)

    def _show_plan(self, plan) -> None:
        self.plan = plan
        self.table.setRowCount(len(plan))
        for row, (f, target, extra) in enumerate(plan):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, check)
            cells = [f.path.name, str(f.path.parent), str(target)] + ([extra] if extra else [])
            for col, text in enumerate(cells, 1):
                if col < len(self.columns):
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    self.table.setItem(row, col, item)
        skipped = len(self.page.groups) and sum(len(g.duplicates) for g in self.page.groups)
        self.summary.setText(f"{len(plan)} files will change." +
                             (f" {skipped} unmoved duplicates are left out." if skipped else ""))

    def apply(self) -> None:
        ticked = [self.plan[r] for r in range(self.table.rowCount())
                  if self.table.item(r, 0).checkState() == Qt.Checked]
        if not ticked:
            return
        if QMessageBox.question(self, "Apply", f"Apply {len(ticked)} changes? "
                                "You can undo them from History.") != QMessageBox.Yes:
            return
        session = Session(self.session_title(len(ticked)))
        moves = [(f, target) for f, target, _ in ticked]
        self.page.run_task("Applying…", lambda t: apply_moves(moves, session, t.progress),
                           lambda errors: self._done(session, errors))

    def _done(self, session, errors) -> None:
        self.page.tree.set_groups(self.page.groups)
        self.page.history_changed.emit()
        self.table.setRowCount(0)
        self.plan = []
        self.summary.setText(f"Done: {len(session.ops)} files changed. Undo from History.")
        if errors:
            QMessageBox.warning(self, "Some files were not changed", "\n".join(errors[:30]))


class DateTab(PlanTab):
    columns = ["Apply", "File", "From", "To", "Date from"]
    apply_label = "Move into date folders"
    apply_icon = "move"

    def build_controls(self, row: QHBoxLayout) -> None:
        self.pattern = QLineEdit(self.settings.date_folder_pattern)
        self.pattern.setToolTip("Fields: {year}, {month:02d}, {day:02d}. "
                                "Example: {year}/{year}-{month:02d}")
        self.dest = QLineEdit()
        self.dest.setPlaceholderText("Same folder that was scanned")
        browse = icons.attach(QPushButton(), "folder")
        browse.setToolTip("Choose a folder")
        browse.clicked.connect(self._browse)
        row.addWidget(QLabel("Folders:"))
        row.addWidget(self.pattern)
        row.addWidget(QLabel("inside:"))
        row.addWidget(self.dest, 1)
        row.addWidget(browse)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Organize into…")
        if d:
            self.dest.setText(d)

    def hint(self) -> str:
        return ("Optional: move photos/videos into folders by the date they were taken "
                "(from the camera's EXIF data, else the file date).")

    def read_controls(self) -> dict:
        return {"pattern": self.pattern.text().strip() or "{year}/{month:02d}",
                "dest": self.dest.text().strip()}

    def make_plan(self, files, opts):
        pattern = opts["pattern"]
        try:
            pattern.format(year=2000, month=1, day=1)
        except (KeyError, ValueError, IndexError):
            raise ValueError(f"Invalid folder pattern: {pattern}")
        self.settings.date_folder_pattern = pattern
        self.settings.save()
        if self.page.category == "videos":
            for f in files:
                if "duration" not in f.info:
                    videos.probe(f)
        dest = Path(opts["dest"]) if opts["dest"] else None
        plan = []
        for f, target in plan_date_moves(files, pattern, dest):
            plan.append((f, target, f"{file_date(f):%Y-%m-%d} ({date_source(f)})"))
        return plan

    def session_title(self, n: int) -> str:
        return f"Organized {n} {self.page.title.lower()} by date"


class TypeTab(PlanTab):
    apply_label = "Sort into type folders"

    def hint(self) -> str:
        return ("Optional: sort documents into PDF, Word, Spreadsheets, Presentations, "
                "Text and eBooks folders inside each scanned folder.")

    def make_plan(self, files, opts):
        return [(f, t, "") for f, t in documents.plan_type_moves(files)]

    def session_title(self, n: int) -> str:
        return f"Sorted {n} documents by type"


class MovieTab(PlanTab):
    columns = ["Apply", "File", "From", "New name", "About"]
    apply_label = "Rename ticked"

    def hint(self) -> str:
        if not self.settings.tmdb_api_key:
            return ("Rename movies to “Title (Year)” and episodes to “Show - S01E02 - Name” "
                    "using TMDb. Add a free TMDb API key in Settings to enable this.")
        return "Rename movies and TV episodes using TMDb. Home videos are left unchanged."

    def make_plan(self, files, opts):
        if not self.settings.tmdb_api_key:
            raise ValueError("Add your free TMDb API key in Settings first "
                             "(themoviedb.org → Settings → API).")
        plan = []
        for f in files:
            prop = videos.identify(f.path, self.settings.tmdb_api_key)
            if prop.apply:
                plan.append((f, f.path.with_name(prop.new_name), prop.description[:200]))
        return plan

    def session_title(self, n: int) -> str:
        return f"Renamed {n} videos from TMDb"
