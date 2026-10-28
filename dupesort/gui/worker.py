"""Run long jobs off the UI thread and report progress back through signals."""

from __future__ import annotations

import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    progress = Signal(int, int, str)
    item = Signal(object)
    finished = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    """Call ``fn(task)``; the function may call ``task.progress()``/``task.emit()``
    and should check ``task.cancelled()`` regularly."""

    _running: set["Task"] = set()  # keep Python wrappers alive until done

    def __init__(self, fn: Callable[["Task"], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self._cancel = False
        self.setAutoDelete(False)

    def progress(self, done: int, total: int, text: str = "") -> None:
        self.signals.progress.emit(done, total, text)

    def emit(self, obj) -> None:
        self.signals.item.emit(obj)

    def cancel(self) -> None:
        self._cancel = True

    def cancelled(self) -> bool:
        return self._cancel

    def run(self) -> None:
        try:
            result = self.fn(self)
        except Exception:
            self.signals.failed.emit(traceback.format_exc())
        else:
            self.signals.finished.emit(result)
        finally:
            Task._running.discard(self)

    def start(self) -> "Task":
        Task._running.add(self)
        QThreadPool.globalInstance().start(self)
        return self
