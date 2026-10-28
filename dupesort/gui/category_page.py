"""One page per media type: choose folders, scan, review and relocate duplicates."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .. import documents, photos, videos
from ..core.duplicates import KEEP_STRATEGIES, DuplicateGroup, choose_keepers
from ..core.history import Session
from ..core.scanner import DUPLICATES_DIR, FileEntry, scan
from ..music import fingerprint
from ..music import organizer as music
from ..settings import Settings
from .widgets import DuplicateTree, FolderList, Preview, human_size
from .worker import Task

ENGINES = {
    "music": (music.find_duplicates, music.quality),
    "photos": (photos.find_duplicates, photos.quality),
    "videos": (videos.find_duplicates, videos.quality),
    "documents": (documents.find_duplicates, documents.quality),
}


class CategoryPage(QWidget):
    history_changed = Signal()

    def __init__(self, category: str, title: str, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.category, self.title, self.settings = category, title, settings
        self.files: list[FileEntry] = []
        self.groups: list[DuplicateGroup] = []
        self.task: Optional[Task] = None
        self._busy_widgets: list[QWidget] = []

        heading = QLabel(f"<h2>{title}</h2>")
        self.folders = FolderList(settings.folders.get(category, []))
        self.folders.changed.connect(self._save_folders)

        src = QGroupBox("Folders to scan")
        QVBoxLayout(src).addWidget(self.folders)

        self.options = QFormLayout()
        self.keep = QComboBox()
        for key, label in KEEP_STRATEGIES.items():
            self.keep.addItem(label, key)
        self.keep.setCurrentIndex(max(0, self.keep.findData(settings.keep_strategy)))
        self.options.addRow("Keep which copy:", self.keep)
        self.add_options(self.options)
        opts = QGroupBox("Options")
        opts.setLayout(self.options)

        top = QHBoxLayout()
        top.addWidget(src, 3)
        top.addWidget(opts, 2)

        self.scan_btn = QPushButton(f"Scan for duplicate {title.lower()}")
        self.scan_btn.setDefault(True)
        self.scan_btn.clicked.connect(self.start_scan)
        self._busy_widgets.append(self.scan_btn)

        # Duplicates tab
        self.tree = DuplicateTree()
        self.preview = Preview(show_images=category == "photos")
        self.preview.show_entry(None)
        self.tree.selected_file.connect(self.preview.show_entry)
        self.tree.keep_changed.connect(self._update_summary)
        split = QSplitter()
        split.addWidget(self.tree)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        self.summary = QLabel("Choose folders and press Scan.")
        self.move_btn = QPushButton(f"Move duplicates to {DUPLICATES_DIR}")
        self.move_btn.setEnabled(False)
        self.move_btn.clicked.connect(self.move_duplicates)
        self._busy_widgets.append(self.move_btn)
        bar = QHBoxLayout()
        bar.addWidget(self.summary, 1)
        bar.addWidget(self.move_btn)
        dup_tab = QWidget()
        dl = QVBoxLayout(dup_tab)
        dl.addWidget(split, 1)
        dl.addLayout(bar)

        self.tabs = QTabWidget()
        self.tabs.addTab(dup_tab, "Duplicates")
        self.add_tabs(self.tabs)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status = QLabel("")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(lambda: self.task and self.task.cancel())
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.progress, 1)
        status_row.addWidget(self.cancel_btn)

        lay = QVBoxLayout(self)
        lay.addWidget(heading)
        notice = self.notice()
        if notice:
            n = QLabel(notice, wordWrap=True, openExternalLinks=True)
            n.setObjectName("notice")
            lay.addWidget(n)
        lay.addLayout(top)
        lay.addWidget(self.scan_btn)
        lay.addWidget(self.tabs, 1)
        lay.addLayout(status_row)

    # --- hooks for subclasses ----------------------------------------------
    def add_options(self, form: QFormLayout) -> None:
        pass

    def add_tabs(self, tabs: QTabWidget) -> None:
        pass

    def notice(self) -> str:
        return ""

    def apply_options(self) -> None:
        """Copy option widgets into ``self.settings`` before a scan."""

    def scan_finished(self) -> None:
        pass

    # --- task plumbing -----------------------------------------------------
    def run_task(self, label: str, fn: Callable[[Task], object],
                 done: Callable[[object], None], on_item: Optional[Callable] = None) -> None:
        if self.task is not None:
            return
        for w in self._busy_widgets:
            w.setEnabled(False)
        self.status.setText(label)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        task = Task(fn)
        task.signals.progress.connect(self._on_progress)
        if on_item:
            task.signals.item.connect(on_item)

        def finish(result):
            self._end_task()
            done(result)

        def fail(tb: str):
            self._end_task()
            last = tb.strip().splitlines()[-1]
            if last.startswith("ValueError: "):  # expected, user-facing problems
                self.status.setText("")
                QMessageBox.warning(self, self.title, last[len("ValueError: "):])
            else:
                self.status.setText("Something went wrong.")
                QMessageBox.critical(self, "Error", tb[-2000:])

        task.signals.finished.connect(finish)
        task.signals.failed.connect(fail)
        self.task = task.start()

    def _on_progress(self, done: int, total: int, text: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        if text:
            self.status.setText(text)

    def _end_task(self) -> None:
        self.task = None
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        for w in self._busy_widgets:
            w.setEnabled(True)
        self.move_btn.setEnabled(bool(self.groups))

    def _save_folders(self) -> None:
        self.settings.folders[self.category] = self.folders.folders()
        self.settings.save()

    # --- scanning ------------------------------------------------------------
    def start_scan(self) -> None:
        roots = [Path(p) for p in self.folders.folders()]
        if not roots:
            QMessageBox.information(self, "No folders", "Add at least one folder to scan.")
            return
        self.apply_options()
        self.settings.keep_strategy = self.keep.currentData()
        self.settings.save()
        find, quality = ENGINES[self.category]
        settings = self.settings

        def job(t: Task):
            files = scan(roots, self.category, min_size=settings.min_size_kb * 1024,
                         exclude=settings.exclude,
                         progress=lambda n, p: t.progress(0, 0, f"Found {n} files…"),
                         cancelled=t.cancelled)
            t.progress(0, len(files), f"Comparing {len(files)} files…")
            groups = find(files, settings, progress=t.progress, cancelled=t.cancelled)
            choose_keepers(groups, settings.keep_strategy, quality)
            return files, groups, t.cancelled()

        self.run_task("Scanning…", job, self._scan_done)

    def _scan_done(self, result) -> None:
        self.files, self.groups, cancelled = result
        self.tree.set_groups(self.groups)
        self._update_summary()
        self.status.setText(("Scan cancelled - partial results. " if cancelled else "") +
                            f"Scanned {len(self.files)} files.")
        self.scan_finished()

    def _update_summary(self) -> None:
        dupes = sum(len(g.duplicates) for g in self.groups)
        wasted = sum(g.wasted_bytes for g in self.groups)
        if not self.groups:
            self.summary.setText("No duplicates found." if self.files else
                                 "Choose folders and press Scan.")
        else:
            self.summary.setText(f"{len(self.groups)} groups · {dupes} duplicates · "
                                 f"{human_size(wasted)} can be freed. Ticked files are kept.")
        self.move_btn.setEnabled(bool(dupes) and self.task is None)

    def move_duplicates(self) -> None:
        moves = [(g, f) for g in self.groups for f in g.duplicates]
        if not moves:
            return
        answer = QMessageBox.question(
            self, "Move duplicates",
            f"Move {len(moves)} duplicate files into a “{DUPLICATES_DIR}” folder inside "
            f"each scanned folder?\n\nNothing is deleted, and you can undo this from History.")
        if answer != QMessageBox.Yes:
            return
        session = Session(f"Moved {len(moves)} duplicate {self.title.lower()}")

        def job(t: Task):
            errors = []
            for n, (_, f) in enumerate(moves, 1):
                if t.cancelled():
                    break
                try:
                    session.move_duplicate(f)
                except OSError as exc:
                    errors.append(f"{f.path}: {exc}")
                t.progress(n, len(moves), f"Moving {f.path.name}")
            return errors

        def done(errors):
            moved = {str(op["src"]) for op in session.ops}
            self.files = [f for f in self.files if str(f.path) not in moved]
            self.groups = [g for g in self.groups
                           if not any(str(f.path) in moved for f in g.files)]
            self.tree.set_groups(self.groups)
            self._update_summary()
            self.status.setText(f"Moved {len(session.ops)} files.")
            self.history_changed.emit()
            if errors:
                QMessageBox.warning(self, "Some files were not moved", "\n".join(errors[:30]))

        self.run_task("Moving duplicates…", job, done)


class MusicPage(CategoryPage):
    def add_options(self, form: QFormLayout) -> None:
        self.by_tags = QCheckBox("Same artist && title (and length)")
        self.by_tags.setChecked(self.settings.music_match_by_tags)
        self.by_sound = QCheckBox("Same sound (acoustic fingerprint)")
        self.by_sound.setChecked(self.settings.music_match_by_fingerprint and fingerprint.available())
        self.by_sound.setEnabled(fingerprint.available())
        form.addRow("Also match:", self.by_tags)
        form.addRow("", self.by_sound)

    def notice(self) -> str:
        if fingerprint.available():
            return ""
        return ("Tip: install <a href='https://acoustid.org/chromaprint'>Chromaprint (fpcalc)</a> "
                "to find the same song across different formats and bitrates by its sound.")

    def apply_options(self) -> None:
        self.settings.music_match_by_tags = self.by_tags.isChecked()
        self.settings.music_match_by_fingerprint = self.by_sound.isChecked()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .music_tab import TagTab

        from .convert_tab import AudioConvertTab

        self.tag_tab = TagTab(self)
        tabs.addTab(self.tag_tab, "Tags, lyrics && rename")
        tabs.addTab(AudioConvertTab(self), "Convert")


class PhotoPage(CategoryPage):
    def add_options(self, form: QFormLayout) -> None:
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 20)
        self.threshold.setValue(self.settings.photo_threshold)
        self.threshold.setToolTip("0 = only identical files. 4-8 catches resized or "
                                  "re-saved copies. Higher values may group similar shots.")
        form.addRow("Similarity tolerance:", self.threshold)

    def apply_options(self) -> None:
        self.settings.photo_threshold = self.threshold.value()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .convert_tab import ImageConvertTab
        from .organize_tab import DateTab

        tabs.addTab(DateTab(self), "Organize by date")
        tabs.addTab(ImageConvertTab(self), "Convert && resize")


class VideoPage(CategoryPage):
    def add_options(self, form: QFormLayout) -> None:
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 20)
        self.threshold.setValue(self.settings.video_threshold)
        self.threshold.setEnabled(videos.ffmpeg_available())
        form.addRow("Similarity tolerance:", self.threshold)

    def notice(self) -> str:
        if videos.ffmpeg_available():
            return ""
        return ("Tip: install <a href='https://ffmpeg.org/download.html'>FFmpeg</a> to also "
                "find re-encoded copies and read recording dates. Without it only "
                "byte-identical videos are found.")

    def apply_options(self) -> None:
        self.settings.video_threshold = self.threshold.value()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .organize_tab import DateTab, MovieTab

        tabs.addTab(DateTab(self), "Organize by date")
        tabs.addTab(MovieTab(self), "Movies && TV names")
        from .convert_tab import VideoConvertTab

        tabs.addTab(VideoConvertTab(self), "Convert && resize")


class DocumentPage(CategoryPage):
    def add_options(self, form: QFormLayout) -> None:
        self.similarity = QSpinBox()
        self.similarity.setRange(50, 100)
        self.similarity.setSuffix(" %")
        self.similarity.setValue(self.settings.document_similarity)
        self.similarity.setToolTip("How much text two documents must share to count as the "
                                   "same document (e.g. a .docx and its exported .pdf).")
        form.addRow("Same text if at least:", self.similarity)

    def apply_options(self) -> None:
        self.settings.document_similarity = self.similarity.value()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .organize_tab import TypeTab

        from .convert_tab import PdfTab

        tabs.addTab(TypeTab(self), "Sort by type")
        tabs.addTab(PdfTab(self), "PDF tools")
