"""One page per media type: choose folders, scan, review and relocate duplicates."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

from .. import documents, photos, videos
from ..core.duplicates import KEEP_STRATEGIES, DuplicateGroup, choose_keepers
from ..core.history import Session
from ..core.scanner import DUPLICATES_DIR, FileEntry, scan
from ..music import fingerprint
from ..music import organizer as music
from ..settings import Settings
from . import icons
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

        # Header: title on the left, the page's main action on the right. Scanning
        # collects the files that every section below works with.
        heading = QLabel(title, objectName="heading")
        sub = QLabel(f"Scan your folders once, then find duplicates{self.subtitle()}.",
                     objectName="muted")
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(heading)
        titles.addWidget(sub)
        self.scan_btn = QPushButton("Scan folders")
        self.scan_btn.setDefault(True)
        self.scan_btn.setToolTip(f"Find all {title.lower()} in the folders below and look for "
                                 "duplicates")
        icons.attach(self.scan_btn, "scan")
        self.scan_btn.clicked.connect(self.start_scan)
        self._busy_widgets.append(self.scan_btn)
        header = QHBoxLayout()
        header.addLayout(titles, 1)
        header.addWidget(self.scan_btn, 0, Qt.AlignBottom)

        # Folders, as removable chips.
        self.folders = FolderList(settings.folders.get(category, []))
        self.folders.changed.connect(self._save_folders)
        folders_row = QHBoxLayout()
        label = QLabel("Folders", objectName="fieldLabel")
        label.setStyleSheet("padding-top: 4px")
        folders_row.addWidget(label, 0, Qt.AlignTop)
        folders_row.addWidget(self.folders, 1)

        # Duplicates section: its options, the results, and its own action.
        self.keep = QComboBox()
        for key, label in KEEP_STRATEGIES.items():
            self.keep.addItem(label, key)
        self.keep.setCurrentIndex(max(0, self.keep.findData(settings.keep_strategy)))
        self.options = QHBoxLayout()
        self.options.setSpacing(8)
        self.add_option("Keep", self.keep)
        self.add_options(self.options)
        self.options.addStretch()

        self.tree = DuplicateTree()
        self.preview = Preview(category)
        self.preview.show_entry(None)
        self.tree.selected_file.connect(self.preview.show_entry)
        if self.preview.player:  # double-click a song or video to play it
            self.tree.itemDoubleClicked.connect(
                lambda item, _col: item.parent() is not None and self.preview.player.play())
        self.tree.keep_changed.connect(self._update_summary)
        split = QSplitter()
        split.addWidget(self.tree)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        self.summary = QLabel("Add folders and press Scan folders.", objectName="muted")
        self.move_btn = QPushButton(f"Move duplicates to {DUPLICATES_DIR}")
        self.move_btn.setEnabled(False)
        icons.attach(self.move_btn, "move")
        self.move_btn.clicked.connect(self.move_duplicates)
        self._busy_widgets.append(self.move_btn)
        bar = QHBoxLayout()
        bar.addWidget(self.summary, 1)
        bar.addWidget(self.move_btn)
        dup_tab = QWidget()
        dl = QVBoxLayout(dup_tab)
        dl.setContentsMargins(0, 12, 0, 0)
        dl.addLayout(self.options)
        dl.addWidget(split, 1)
        dl.addLayout(bar)

        # Sections, shown as a segmented switch.
        self.tabs = QTabWidget(objectName="sections")
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()  # the compact switch below stands in for it
        self.tabs.addTab(dup_tab, "Duplicates")
        self.add_tabs(self.tabs)
        self.switch = QTabBar(objectName="segments")
        self.switch.setDrawBase(False)
        self.switch.setExpanding(False)
        self.switch.setUsesScrollButtons(False)
        for i in range(self.tabs.count()):
            self.switch.addTab(self.tabs.tabText(i))
        self.switch.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.switch.setCurrentIndex)
        self.tabs.currentChanged.connect(self._section_changed)
        switch_row = QHBoxLayout()
        switch_row.addWidget(self.switch)
        switch_row.addStretch()

        # Progress for whatever is running, at the bottom of the page.
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status = QLabel("", objectName="muted")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        icons.attach(self.cancel_btn, "close")
        self.cancel_btn.clicked.connect(lambda: self.task and self.task.cancel())
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.progress, 1)
        status_row.addWidget(self.cancel_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addLayout(header)
        lay.addLayout(folders_row)
        notice = self.notice()
        if notice:
            n = QLabel(notice, wordWrap=True, openExternalLinks=True)
            n.setObjectName("notice")
            lay.addWidget(n)
        lay.addSpacing(4)
        lay.addLayout(switch_row)
        lay.addWidget(self.tabs, 1)
        lay.addLayout(status_row)

    def _section_changed(self, index: int) -> None:
        """Scan is the filled main button only in Duplicates; other sections have their own."""
        self.scan_btn.setDefault(index == 0)
        self.scan_btn.style().unpolish(self.scan_btn)
        self.scan_btn.style().polish(self.scan_btn)
        icons.attach(self.scan_btn, "scan")

    def add_option(self, label: str, widget: QWidget) -> None:
        """Add ``label`` + ``widget`` to the Duplicates section's option row."""
        if label:
            self.options.addSpacing(10 if self.options.count() else 0)
            self.options.addWidget(QLabel(label, objectName="fieldLabel"))
        self.options.addWidget(widget)

    def subtitle(self) -> str:
        """Extra words for the line under the title, e.g. ", fix tags or convert"."""
        return ""

    # --- hooks for subclasses ----------------------------------------------
    def add_options(self, row: QHBoxLayout) -> None:
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
                                 "Add folders and press Scan folders.")
        else:
            g, d = len(self.groups), dupes
            self.summary.setText(f"{g} group{'s' * (g != 1)} · {d} duplicate{'s' * (d != 1)} · "
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
    def subtitle(self) -> str:
        return ", fix tags and lyrics, or convert"

    def add_options(self, row: QHBoxLayout) -> None:
        self.by_tags = QCheckBox("Same artist && title")
        self.by_tags.setToolTip("Same artist, title and length (within 3 seconds)")
        self.by_tags.setChecked(self.settings.music_match_by_tags)
        self.by_sound = QCheckBox("Same sound")
        self.by_sound.setToolTip("Acoustic fingerprint: finds the same recording in "
                                 "different formats and bitrates")
        self.by_sound.setChecked(self.settings.music_match_by_fingerprint and fingerprint.available())
        self.by_sound.setEnabled(fingerprint.available())
        self.versions = QCheckBox("Keep versions apart")
        self.versions.setToolTip(
            "Live, acoustic, unplugged, remix, demo, instrumental and other versions of a song "
            "are not duplicates of each other.\nThe version is read from the title, the file "
            "name, the album, the genre and the folder name.")
        self.versions.setChecked(self.settings.music_separate_versions)
        self.add_option("Match", self.by_tags)
        self.add_option("", self.by_sound)
        self.add_option("", self.versions)

    def notice(self) -> str:
        if fingerprint.available():
            return ""
        return ("Tip: install <a href='https://acoustid.org/chromaprint'>Chromaprint (fpcalc)</a> "
                "to find the same song across different formats and bitrates by its sound.")

    def apply_options(self) -> None:
        self.settings.music_match_by_tags = self.by_tags.isChecked()
        self.settings.music_match_by_fingerprint = self.by_sound.isChecked()
        self.settings.music_separate_versions = self.versions.isChecked()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .music_tab import TagTab

        from .convert_tab import AudioConvertTab

        self.tag_tab = TagTab(self)
        tabs.addTab(self.tag_tab, "Tags, lyrics && rename")
        tabs.addTab(AudioConvertTab(self), "Convert")


class PhotoPage(CategoryPage):
    def subtitle(self) -> str:
        return ", sort by date, or convert and resize"

    def add_options(self, row: QHBoxLayout) -> None:
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 20)
        self.threshold.setValue(self.settings.photo_threshold)
        self.threshold.setToolTip("0 = only identical files. 4-8 catches resized or "
                                  "re-saved copies. Higher values may group similar shots.")
        self.add_option("Tolerance", self.threshold)

    def apply_options(self) -> None:
        self.settings.photo_threshold = self.threshold.value()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .convert_tab import ImageConvertTab
        from .organize_tab import DateTab

        tabs.addTab(DateTab(self), "Organize by date")
        tabs.addTab(ImageConvertTab(self), "Convert && resize")


class VideoPage(CategoryPage):
    def subtitle(self) -> str:
        return ", sort and rename, or convert"

    def add_options(self, row: QHBoxLayout) -> None:
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 20)
        self.threshold.setValue(self.settings.video_threshold)
        self.threshold.setEnabled(videos.ffmpeg_available())
        self.add_option("Tolerance", self.threshold)

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
    def subtitle(self) -> str:
        return ", sort by type, or use the PDF tools"

    def add_options(self, row: QHBoxLayout) -> None:
        self.similarity = QSpinBox()
        self.similarity.setRange(50, 100)
        self.similarity.setSuffix(" %")
        self.similarity.setValue(self.settings.document_similarity)
        self.similarity.setToolTip("How much text two documents must share to count as the "
                                   "same document (e.g. a .docx and its exported .pdf).")
        self.add_option("Same text if at least", self.similarity)

    def apply_options(self) -> None:
        self.settings.document_similarity = self.similarity.value()

    def add_tabs(self, tabs: QTabWidget) -> None:
        from .organize_tab import TypeTab

        from .convert_tab import PdfTab

        tabs.addTab(TypeTab(self), "Sort by type")
        tabs.addTab(PdfTab(self), "PDF tools")
