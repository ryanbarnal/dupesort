import math
import struct
import wave
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Keep history and settings out of the real user folders."""
    monkeypatch.setenv("DUPESORT_DATA", str(tmp_path / "_appdata"))
    monkeypatch.setenv("DUPESORT_CONFIG", str(tmp_path / "_config"))
    monkeypatch.setenv("DUPESORT_NO_UPDATE_CHECK", "1")  # no GitHub calls from tests


def make_wav(path: Path, freq: float = 440.0, seconds: float = 1.0, rate: int = 8000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
                          for i in range(int(rate * seconds)))
        w.writeframes(frames)
    return path
