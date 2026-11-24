"""Music: look up tags & lyrics online, review uncertain matches, apply and rename."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.history import Session
from ..music import organizer
from ..music.lookup import Match, Proposal
from ..music.tags import format_name
from . import icons
from .license_dialog import require as require_license

EDIT_FIELDS = ("title", "artist", "album", "albumartist", "genre", "date", "tracknumber")
COLUMNS = ["Apply", "File", "Current", "Suggested", "Genre", "Lyrics", "Match", "Status"]


def _pair(tags: dict) -> str:
    if not tags.get("title"):
        return "—"
    return f"{tags.get('artist', '?')} – {tags['title']}"


class TagTab(QWidget):
    def __init__(self, page) -> None:
        super().__init__()
        self.page = page
        self.settings = page.settings
        self.proposals: list[Proposal] = []
        self._filling = False

        self.scope = QComboBox()
        self.scope.addItems(["Songs with missing details", "All scanned songs"])
        self.lookup_btn = QPushButton("Look up tags && lyrics online")
        icons.attach(self.lookup_btn, "globe")
        self.lookup_btn.clicked.connect(self.start_lookup)
        self.rename_after = QCheckBox()
        self.rename_after.setChecked(True)
        self._update_rename_label()
        top = QHBoxLayout()
        top.addWidget(QLabel("Songs:"))
        top.addWidget(self.scope)
        top.addWidget(self.lookup_btn)
        top.addStretch()
        top.addWidget(self.rename_after)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        # Short columns hug their text and the name columns share the rest, so
        # the Status column is always on screen. Cut-off names show as tooltips.
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        for col in (COLUMNS.index("File"), COLUMNS.index("Current"), COLUMNS.index("Suggested")):
            h.setSectionResizeMode(col, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(lambda r, *_: self._show_details(r))

        # Details / manual correction panel
        self.candidates = QComboBox()
        self.candidates.activated.connect(self._choose_candidate)
        self.fields = {name: QLineEdit() for name in EDIT_FIELDS}
        self.lyrics = QPlainTextEdit()
        self.lyrics.setPlaceholderText("Lyrics (fetched from LRCLIB, or paste your own)")
        save = QPushButton("Use these details")
        icons.attach(save, "check")
        save.clicked.connect(self._save_edits)
        form = QFormLayout()
        form.addRow("Online matches:", self.candidates)
        for name, edit in self.fields.items():
            label = {"albumartist": "Album artist", "tracknumber": "Track #"}.get(name, name.title())
            form.addRow(label + ":", edit)
        details = QWidget()
        dl = QVBoxLayout(details)
        dl.addLayout(form)
        dl.addWidget(QLabel("Lyrics:"))
        dl.addWidget(self.lyrics, 1)
        dl.addWidget(save)
        details.setMinimumWidth(300)
        details.setEnabled(False)
        self.details = details

        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        self.summary = QLabel("Scan a folder first, then look up songs online.")
        self.apply_btn = QPushButton("Apply ticked")
        icons.attach(self.apply_btn, "check")
        self.apply_btn.clicked.connect(self.apply)
        self.rename_btn = QPushButton("Rename all scanned songs (no lookup)")
        icons.attach(self.rename_btn, "pencil")
        self.rename_btn.setToolTip("Rename using each file's existing tags.")
        self.rename_btn.clicked.connect(self.rename_all)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.rename_btn)
        bottom.addWidget(self.apply_btn)
        page._busy_widgets += [self.lookup_btn, self.apply_btn, self.rename_btn]

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)

    def _update_rename_label(self) -> None:
        self.rename_after.setText(
            f"Rename files to “{self.settings.music_rename_pattern}” after applying")

    # --- lookup --------------------------------------------------------------
    def _targets(self):
        files = self.page.files
        if self.scope.currentIndex() == 0:
            needed = ("title", "artist", "album", "genre")
            files = [f for f in files
                     if any(not (f.info.get("tags") or {}).get(k) for k in needed)
                     or (self.settings.fetch_lyrics and not (f.info.get("tags") or {}).get("lyrics"))]
        return files

    def start_lookup(self) -> None:
        self._update_rename_label()
        if not self.page.files:
            QMessageBox.information(self, "Scan first",
                                    "Scan your music folders first - the scan reads every "
                                    "song's current tags.")
            return
        targets = self._targets()
        if not targets:
            QMessageBox.information(self, "Nothing to do", "Every song already has its details.")
            return
        self.proposals = []
        self.table.setRowCount(0)
        settings = self.settings

        def job(t):
            for n, f in enumerate(targets, 1):
                if t.cancelled():
                    break
                t.progress(n - 1, len(targets), f"Looking up {f.path.name} ({n}/{len(targets)})")
                t.emit(organizer.build_proposal(f.path, settings))
            return len(targets)

        self.page.run_task("Looking up songs online…", job, self._lookup_done, self._add_proposal)

    def export_state(self) -> list:
        return list(self.proposals)

    def restore_state(self, proposals: list) -> None:
        self.proposals = list(proposals)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.proposals))
        for row in range(len(self.proposals)):
            self._fill_row(row)
        if self.proposals:
            self._update_summary()

    def _add_proposal(self, prop: Proposal) -> None:
        self.proposals.append(prop)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._fill_row(row)
        self._update_summary()
        self.page.schedule_save()

    def _lookup_done(self, _total) -> None:
        self._update_summary()
        self.page.status.setText("Lookup finished. Review the orange rows, then press Apply.")

    def _fill_row(self, row: int) -> None:
        p = self.proposals[row]
        new = p.proposed()
        if p.error and not p.match:
            status, color = p.error, QColor("#888888")
        elif p.done:
            status, color = "Applied", QColor("#2e7d32")
        elif p.confidence >= self.settings.auto_apply_confidence:
            status, color = "Confident", QColor("#2e7d32")
        else:
            status, color = "Please review", QColor("#e65100")
        cells = ["", p.path.name, _pair(p.current), _pair(new) +
                 (f"  ({new['album']})" if new.get("album") else ""),
                 new.get("genre", ""), "yes" if new.get("lyrics") else "",
                 f"{p.confidence}%" if p.match else "", status]
        self._filling = True
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(text if col != 1 else str(p.path))
            if col == 0:
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked if p.apply else Qt.Unchecked)
                if not p.match or p.done:
                    item.setFlags(Qt.ItemIsSelectable)
            if col == 7:
                item.setForeground(color)
            self.table.setItem(row, col, item)
        self._filling = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 0:
            return
        self.proposals[item.row()].apply = item.checkState() == Qt.Checked
        self._update_summary()
        self.page.schedule_save()

    def _update_summary(self) -> None:
        ticked = sum(p.apply and not p.done for p in self.proposals)
        review = sum(bool(p.match) and p.confidence < self.settings.auto_apply_confidence
                     and not p.done for p in self.proposals)
        missing = sum(not p.match for p in self.proposals)
        self.summary.setText(f"{len(self.proposals)} looked up · {ticked} ticked to apply · "
                             f"{review} need review · {missing} not found")
        self.apply_btn.setText(f"Apply ticked ({ticked})")

    # --- details panel ---------------------------------------------------------
    def _show_details(self, row: int) -> None:
        if not 0 <= row < len(self.proposals):
            self.details.setEnabled(False)
            return
        p = self.proposals[row]
        self.details.setEnabled(not p.done)
        self.candidates.clear()
        for m in p.matches:
            self.candidates.addItem(f"{m.label()}  [{m.source}]")
        if p.matches:
            self.candidates.setCurrentIndex(p.chosen)
        new = p.proposed()
        for name, edit in self.fields.items():
            edit.setText(new.get(name, ""))
        self.lyrics.setPlainText(new.get("lyrics", ""))

    def _choose_candidate(self, index: int) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.proposals):
            return
        p, settings = self.proposals[row], self.settings

        def job(t):
            organizer.choose_match(p, index, settings)

        def done(_):
            self._fill_row(row)
            self._show_details(row)
            self._update_summary()

        self.page.run_task("Fetching details…", job, done)

    def _save_edits(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.proposals):
            return
        p = self.proposals[row]
        tags = {k: e.text().strip() for k, e in self.fields.items() if e.text().strip()}
        release = p.match.release_id if p.match else ""
        p.matches.insert(0, Match(100, tags, source="Edited by you", release_id=release))
        p.chosen = 0
        p.edited_lyrics = self.lyrics.toPlainText().strip()
        p.apply = True
        p.error = ""
        self._fill_row(row)
        self._update_summary()
        self.page.schedule_save()

    # --- applying ------------------------------------------------------------
    def _entry_for(self, path):
        return next((f for f in self.page.files if f.path == path), None)

    def apply(self) -> None:
        if not require_license(self, "write tags and rename songs"):
            return
        todo = [p for p in self.proposals if p.apply and p.match and not p.done]
        if not todo:
            return
        rename = self.rename_after.isChecked()
        session = Session(f"Tagged {len(todo)} songs" + (" and renamed" if rename else ""))
        settings = self.settings

        def job(t):
            errors = []
            for n, p in enumerate(todo, 1):
                if t.cancelled():
                    break
                t.progress(n - 1, len(todo), f"Writing tags: {p.path.name}")
                try:
                    old = p.path
                    p.path = organizer.apply_proposal(p, session, settings, rename)
                    p.done = True
                    f = self._entry_for(old)
                    if f:
                        f.path, f.info["tags"] = p.path, p.proposed()
                except Exception as exc:
                    errors.append(f"{p.path.name}: {exc}")
            return errors

        def done(errors):
            for row in range(len(self.proposals)):
                self._fill_row(row)
            self._update_summary()
            self.page.schedule_save()
            self.page.tree.set_groups(self.page.groups)
            self.page.history_changed.emit()
            self.page.status.setText(f"Updated {sum(p.done for p in todo)} songs.")
            if errors:
                QMessageBox.warning(self, "Some songs were not updated", "\n".join(errors[:30]))

        self.page.run_task("Writing tags…", job, done)

    def rename_all(self) -> None:
        if not require_license(self, "rename songs"):
            return
        files = list(self.page.files)
        if not files:
            QMessageBox.information(self, "Scan first", "Scan your music folders first.")
            return
        pattern = self.settings.music_rename_pattern
        planned = [(f, format_name(pattern, f.info.get("tags") or {}, f.path.suffix.lower()))
                   for f in files]
        planned = [(f, n) for f, n in planned if n and n != f.path.name]
        skipped = len(files) - len(planned)
        if not planned:
            QMessageBox.information(self, "Nothing to rename",
                                    "All songs already match the pattern, or are missing the "
                                    "tags it needs. Try looking them up online first.")
            return
        sample = "\n".join(f"{f.path.name}  →  {n}" for f, n in planned[:8])
        if QMessageBox.question(self, "Rename songs",
                                f"Rename {len(planned)} songs to “{pattern}”?\n\n{sample}"
                                + ("\n…" if len(planned) > 8 else "")
                                + (f"\n\n{skipped} songs are skipped (already named or "
                                   "missing tags)." if skipped else "")) != QMessageBox.Yes:
            return
        session = Session(f"Renamed {len(planned)} songs")

        def job(t):
            errors = []
            for n, (f, name) in enumerate(planned, 1):
                try:
                    f.path = session.rename(f.path, name)
                except OSError as exc:
                    errors.append(f"{f.path.name}: {exc}")
                t.progress(n, len(planned), f.path.name)
            return errors

        def done(errors):
            self.page.tree.set_groups(self.page.groups)
            self.page.history_changed.emit()
            self.page.status.setText(f"Renamed {len(planned) - len(errors)} songs.")
            if errors:
                QMessageBox.warning(self, "Some songs were not renamed", "\n".join(errors[:30]))

        self.page.run_task("Renaming…", job, done)
