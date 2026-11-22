"""User settings persisted as JSON in the platform's config folder."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from platformdirs import user_config_dir

from . import APP_NAME


@dataclass
class Settings:
    # Online services
    tmdb_api_key: str = ""
    acoustid_api_key: str = ""
    fetch_cover_art: bool = True
    fetch_lyrics: bool = True
    # Music
    music_rename_pattern: str = "{artist} - {title}"
    music_match_by_tags: bool = True
    music_match_by_fingerprint: bool = True
    auto_apply_confidence: int = 90  # 0-100; lower-scored matches go to review
    # Photos / videos
    photo_threshold: int = 6  # perceptual-hash bit difference, 0 = identical
    video_threshold: int = 10
    date_folder_pattern: str = "{year}/{month:02d}"
    # Documents
    document_similarity: int = 90  # percent of shared text
    # Appearance
    theme_mode: str = "System"  # System / Light / Dark
    accent: str = "Mono"
    play_intro: bool = True
    # General
    keep_strategy: str = "best"
    min_size_kb: int = 1
    exclude: list[str] = field(default_factory=list)
    folders: dict[str, list[str]] = field(default_factory=dict)

    @staticmethod
    def path() -> Path:
        base = os.environ.get("DUPESORT_CONFIG", user_config_dir(APP_NAME, False))
        return Path(base) / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
