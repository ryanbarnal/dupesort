"""Documents: exact duplicates and the same text saved in different files/formats."""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

from .core.duplicates import DuplicateGroup, merge_groups
from .core.hashing import find_exact_duplicates
from .core.scanner import FileEntry

MAX_TEXT = 2_000_000
NUM_PERM, BANDS = 128, 32
ROWS = NUM_PERM // BANDS
_MASK = (1 << 61) - 1
_SEEDS = [int.from_bytes(hashlib.blake2b(str(i).encode(), digest_size=8).digest(), "big")
          for i in range(NUM_PERM)]

TYPE_FOLDERS = {
    "PDF": {".pdf"},
    "Word": {".doc", ".docx", ".odt", ".rtf"},
    "Spreadsheets": {".xls", ".xlsx", ".ods", ".csv"},
    "Presentations": {".ppt", ".pptx", ".odp"},
    "Text": {".txt", ".md"},
    "eBooks": {".epub"},
}

_ZIP_PARTS = {
    ".docx": re.compile(r"word/(document|header\d*|footer\d*)\.xml$"),
    ".pptx": re.compile(r"ppt/slides/slide\d+\.xml$"),
    ".xlsx": re.compile(r"xl/sharedStrings\.xml$"),
    ".odt": re.compile(r"content\.xml$"), ".ods": re.compile(r"content\.xml$"),
    ".odp": re.compile(r"content\.xml$"),
    ".epub": re.compile(r".*\.x?html?$"),
}


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md", ".csv"):
            return path.read_bytes()[:MAX_TEXT].decode("utf-8", "ignore")
        if ext == ".rtf":
            raw = path.read_bytes()[:MAX_TEXT].decode("latin-1", "ignore")
            raw = re.sub(r"\\'[0-9a-f]{2}|\\[a-z]+-?\d* ?|[{}]", " ", raw)
            return raw
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:50])
        if ext in _ZIP_PARTS:
            pattern, chunks = _ZIP_PARTS[ext], []
            with zipfile.ZipFile(path) as z:
                for name in sorted(z.namelist()):
                    if pattern.search(name):
                        xml = z.read(name)[:MAX_TEXT].decode("utf-8", "ignore")
                        # Paragraph-ish tags become spaces so words don't run together.
                        chunks.append(re.sub(r"<[^>]+>", " ", xml))
            return " ".join(chunks)
    except Exception:
        return ""
    return ""  # legacy binary formats (.doc/.xls/.ppt): exact matching only


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def minhash(text: str, shingle: int = 5) -> Optional[list[int]]:
    words = _words(text)
    if len(words) < 30:  # too short to compare meaningfully
        return None
    shingles = {hash(" ".join(words[i:i + shingle])) & _MASK
                for i in range(len(words) - shingle + 1)}
    return [min(((s ^ seed) * 0x9E3779B97F4A7C15) & _MASK for s in shingles) for seed in _SEEDS]


def estimated_similarity(a: list[int], b: list[int]) -> float:
    return sum(x == y for x, y in zip(a, b)) / len(a)


def find_duplicates(files: list[FileEntry], settings,
                    progress: Optional[Callable[[int, int, str], None]] = None,
                    cancelled: Callable[[], bool] = lambda: False) -> list[DuplicateGroup]:
    found = [("Identical file", find_exact_duplicates(files, cancelled=cancelled))]
    sigs: dict[int, list[int]] = {}
    for n, f in enumerate(files):
        if cancelled():
            return merge_groups(found)
        sig = minhash(extract_text(f.path))
        if sig:
            sigs[n] = sig
        if progress and n % 5 == 0:
            progress(n + 1, len(files), f"Reading: {f.path.name}")

    # Locality-sensitive hashing: only compare documents sharing a band.
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for n, sig in sigs.items():
        for b in range(BANDS):
            buckets[(b, tuple(sig[b * ROWS:(b + 1) * ROWS]))].append(n)
    threshold = settings.document_similarity / 100
    checked, pairs = set(), []
    for members in buckets.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if (a, b) in checked:
                    continue
                checked.add((a, b))
                if estimated_similarity(sigs[a], sigs[b]) >= threshold:
                    pairs.append([files[a], files[b]])
    found.append(("Same text", pairs))
    return merge_groups(found)


def quality(f: FileEntry) -> tuple:
    # Prefer editable formats, then the most recently modified copy.
    ext = f.path.suffix.lower()
    editable = ext in {".docx", ".odt", ".xlsx", ".ods", ".pptx", ".odp", ".md", ".txt"}
    return (editable, f.mtime)


def plan_type_moves(files: list[FileEntry]) -> list[tuple[FileEntry, Path]]:
    moves = []
    for f in files:
        ext = f.path.suffix.lower()
        folder = next((name for name, exts in TYPE_FOLDERS.items() if ext in exts), "Other")
        target = f.root / folder / f.path.name
        if target.parent.resolve() != f.path.parent.resolve():
            moves.append((f, target))
    return moves
