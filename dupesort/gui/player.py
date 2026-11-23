"""A small player for the preview panel, to compare duplicate songs and videos."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from . import icons


def _time(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class MiniPlayer(QWidget):
    """Play / pause, a seek bar and the time. Uses Qt Multimedia, loaded on first use."""

    def __init__(self, video: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.path: Optional[Path] = None
        # For videos, a picture area the preview panel places above its details.
        self.video = None
        if video:
            try:
                from PySide6.QtMultimediaWidgets import QVideoWidget

                self.video = QVideoWidget()
                self.video.setMinimumSize(240, 150)
                self.video.setStyleSheet("background: black; border-radius: 6px;")
                self.video.setVisible(False)
            except ImportError:
                self.video = None
        self._player = None
        self._audio = None
        self._seeking = False
        self.play_btn = QPushButton()
        self.play_btn.setToolTip("Play (or double-click a file in the list)")
        self.play_btn.setFixedWidth(40)
        icons.attach(self.play_btn, "play")
        self.play_btn.clicked.connect(self.toggle)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_done)
        self.time = QLabel("0:00", objectName="muted")
        self.time.setMinimumWidth(78)
        self.time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.play_btn)
        lay.addWidget(self.seek, 1)
        lay.addWidget(self.time)
        self.setEnabled(False)

    # --- Qt Multimedia, created only when something is played ---------------------------------
    def _ensure(self) -> bool:
        if self._player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            self.play_btn.setToolTip("Playing needs Qt Multimedia, which isn't installed")
            return False
        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        if self.video is not None:
            self._player.setVideoOutput(self.video)
        self._player.durationChanged.connect(self._duration)
        self._player.positionChanged.connect(self._position)
        self._player.playbackStateChanged.connect(self._state)
        self._player.errorOccurred.connect(self._error)
        if self.path:
            self._player.setSource(QUrl.fromLocalFile(str(self.path)))
        return True

    @property
    def playing(self) -> bool:
        if self._player is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer

        return self._player.playbackState() == QMediaPlayer.PlayingState

    def load(self, path: Optional[Path]) -> None:
        """Show ``path`` in the player. If a song was playing, the new one starts playing,
        so you can click through a group and hear each copy."""
        was_playing = self.playing
        self.path = path
        self.setEnabled(path is not None)
        if self.video is not None and not (was_playing and path):
            self.video.setVisible(False)
        self.seek.setRange(0, 0)
        self.time.setText("0:00")
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(str(path)) if path else QUrl())
            if was_playing and path:
                self._player.play()

    def play(self) -> None:
        if self.path and self._ensure():
            if self.video is not None:
                self.video.setVisible(True)
            self._player.play()

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()

    def toggle(self) -> None:
        if self.playing:
            self._player.pause()
        else:
            self.play()

    # --- signals ---------------------------------------------------------------------------------
    def _duration(self, ms: int) -> None:
        self.seek.setRange(0, ms)
        self._position(self._player.position())

    def _position(self, ms: int) -> None:
        if not self._seeking:
            self.seek.setValue(ms)
        total = self._player.duration() if self._player else 0
        self.time.setText(f"{_time(ms)} / {_time(total)}" if total else _time(ms))

    def _seek_done(self) -> None:
        self._seeking = False
        if self._player is not None:
            self._player.setPosition(self.seek.value())

    def _state(self, _state) -> None:
        icons.attach(self.play_btn, "pause" if self.playing else "play")
        self.play_btn.setToolTip("Pause" if self.playing else "Play")

    def _error(self, _err, message: str = "") -> None:
        self.time.setText("Can't play")
        self.play_btn.setToolTip(message or "This file can't be played here")
