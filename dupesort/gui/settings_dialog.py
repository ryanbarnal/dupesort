"""Settings window: online-service keys, naming patterns and scan filters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QSpinBox, QVBoxLayout,
)

from ..music.tags import format_name
from . import theme
from ..settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings
        s = settings

        online = QFormLayout()
        self.tmdb = QLineEdit(s.tmdb_api_key)
        self.tmdb.setPlaceholderText("Optional - for movie/TV names")
        self.acoustid = QLineEdit(s.acoustid_api_key)
        self.acoustid.setPlaceholderText("Optional - identify untagged songs by sound")
        self.cover = QCheckBox("Embed album cover art")
        self.cover.setChecked(s.fetch_cover_art)
        self.lyrics = QCheckBox("Fetch lyrics and embed them in the file")
        self.lyrics.setChecked(s.fetch_lyrics)
        self.confidence = QSpinBox()
        self.confidence.setRange(50, 100)
        self.confidence.setSuffix(" %")
        self.confidence.setValue(s.auto_apply_confidence)
        self.confidence.setToolTip("Matches at or above this score are ticked automatically; "
                                   "the rest are left for you to review.")
        online.addRow("TMDb API key:", self.tmdb)
        online.addRow(QLabel("<small>Free at <a href='https://www.themoviedb.org/settings/api'>"
                             "themoviedb.org</a></small>", openExternalLinks=True))
        online.addRow("AcoustID API key:", self.acoustid)
        online.addRow(QLabel("<small>Free at <a href='https://acoustid.org/new-application'>"
                             "acoustid.org</a> (needs Chromaprint/fpcalc installed)</small>",
                             openExternalLinks=True))
        online.addRow("", self.cover)
        online.addRow("", self.lyrics)
        online.addRow("Auto-apply matches above:", self.confidence)
        online_box = QGroupBox("Music && video information from the web")
        online_box.setLayout(online)

        naming = QFormLayout()
        self.pattern = QLineEdit(s.music_rename_pattern)
        self.pattern.setToolTip("Fields: {artist} {title} {album} {albumartist} {genre} "
                                "{date} {tracknumber}")
        self.example = QLabel()
        self.pattern.textChanged.connect(self._update_example)
        self._update_example()
        naming.addRow("Music file name:", self.pattern)
        naming.addRow("", self.example)
        naming_box = QGroupBox("Naming")
        naming_box.setLayout(naming)

        scan = QFormLayout()
        self.min_size = QSpinBox()
        self.min_size.setRange(0, 1_000_000)
        self.min_size.setSuffix(" KB")
        self.min_size.setValue(s.min_size_kb)
        self.exclude = QLineEdit(", ".join(s.exclude))
        self.exclude.setPlaceholderText("e.g. Backups, Podcasts")
        scan.addRow("Ignore files smaller than:", self.min_size)
        scan.addRow("Skip paths containing:", self.exclude)
        scan_box = QGroupBox("Scanning")
        scan_box.setLayout(scan)

        look = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(theme.MODES)
        self.mode.setCurrentText(s.theme_mode)
        self.accent = QComboBox()
        self.accent.addItems(list(theme.ACCENTS))
        self.accent.setCurrentText(s.accent)
        self.intro = QCheckBox("Play the animated intro at start-up")
        self.intro.setChecked(s.play_intro)
        look.addRow("Light / dark:", self.mode)
        look.addRow("Accent colour:", self.accent)
        look.addRow("", self.intro)
        self.updates = QCheckBox("Check for new versions automatically")
        self.updates.setChecked(s.check_updates)
        look.addRow("Updates:", self.updates)
        look_box = QGroupBox("Appearance")
        look_box.setLayout(look)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        for w in (look_box, online_box, naming_box, scan_box):
            lay.addWidget(w)
        lay.addWidget(buttons)

    def _update_example(self) -> None:
        demo = {"artist": "Queen", "title": "Bohemian Rhapsody", "album": "A Night at the Opera",
                "albumartist": "Queen", "genre": "Rock", "date": "1975", "tracknumber": "11"}
        name = format_name(self.pattern.text(), demo, ".mp3")
        self.example.setText(f"<small>Example: {name}</small>" if name else
                             "<small style='color:#c62828'>Invalid pattern</small>")

    def accept(self) -> None:
        s = self.settings
        s.tmdb_api_key = self.tmdb.text().strip()
        s.acoustid_api_key = self.acoustid.text().strip()
        s.fetch_cover_art = self.cover.isChecked()
        s.fetch_lyrics = self.lyrics.isChecked()
        s.auto_apply_confidence = self.confidence.value()
        if format_name(self.pattern.text(), {"artist": "a", "title": "t"}, ".mp3"):
            s.music_rename_pattern = self.pattern.text().strip()
        s.min_size_kb = self.min_size.value()
        s.exclude = [e.strip() for e in self.exclude.text().split(",") if e.strip()]
        s.theme_mode = self.mode.currentText()
        s.accent = self.accent.currentText()
        s.play_intro = self.intro.isChecked()
        s.check_updates = self.updates.isChecked()
        s.save()
        super().accept()
