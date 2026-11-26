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
    "Drawings": {".dwg", ".dxf"},
}

# Documents shorter than this must have exactly the same text to match: in drawings, forms
# and letterheads the shared boilerplate is most of the text.
SHORT_WORDS = 200
# How alike two PDFs' first pages must look (share of drawn ink that lines up).
PAGE_MATCH = 0.90

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


def pdf_look(path: Path, width: int = 300):
    """(page count, ink mask of page 1) for a PDF: what it looks like, not what it says."""
    try:
        import pypdfium2 as pdfium
        from PIL import ImageFilter

        doc = pdfium.PdfDocument(str(path))
        try:
            pages = len(doc)
            page = doc[0]
            img = page.render(scale=width / max(1.0, page.get_width())).to_pil().convert("L")
        finally:
            doc.close()
        ink = img.point(lambda v: 255 if v < 160 else 0)
        # Thicken a little, so the same drawing written by another PDF program still lines up.
        return pages, ink, ink.filter(ImageFilter.MaxFilter(3))
    except Exception:
        return None


def pages_look_alike(a, b) -> bool:
    """Do two PDFs (from ``pdf_look``) look the same? Same page count, and nearly all ink
    on each first page falls where the other has ink too."""
    if a is None or b is None:
        return False
    pages_a, ink_a, thick_a = a
    pages_b, ink_b, thick_b = b
    if pages_a != pages_b:
        return False
    if ink_a.size != ink_b.size:
        thick_b, ink_b = thick_b.resize(ink_a.size), ink_b.resize(ink_a.size)
    from PIL import ImageChops

    def count(img) -> int:
        return sum(img.histogram()[128:])

    total = count(ink_a) + count(ink_b)
    if total == 0:
        return True  # two blank first pages
    matched = (count(ImageChops.multiply(ink_a, thick_b)) +
               count(ImageChops.multiply(ink_b, thick_a)))
    return matched / total >= PAGE_MATCH


def find_duplicates(files: list[FileEntry], settings,
                    progress: Optional[Callable[[int, int, str], None]] = None,
                    cancelled: Callable[[], bool] = lambda: False) -> list[DuplicateGroup]:
    found = [("Identical file", find_exact_duplicates(files, cancelled=cancelled))]
    sigs: dict[int, list[int]] = {}
    words: dict[int, tuple[int, int]] = {}  # word count, hash of the exact words
    for n, f in enumerate(files):
        if cancelled():
            return merge_groups(found)
        text = extract_text(f.path)
        sig = minhash(text)
        if sig:
            sigs[n] = sig
            w = _words(text)
            words[n] = (len(w), hash(tuple(w)))
        if progress and n % 5 == 0:
            progress(n + 1, len(files), f"Reading: {f.path.name}")

    # Locality-sensitive hashing: only compare documents sharing a band.
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for n, sig in sigs.items():
        for b in range(BANDS):
            buckets[(b, tuple(sig[b * ROWS:(b + 1) * ROWS]))].append(n)
    threshold = settings.document_similarity / 100
    looks: dict[int, object] = {}

    def look(n: int):
        if n not in looks:
            looks[n] = pdf_look(files[n].path)
        return looks[n]

    def same_document(a: int, b: int) -> bool:
        if estimated_similarity(sigs[a], sigs[b]) < threshold:
            return False
        # Short texts are mostly boilerplate (a drawing's title block, a form): only the very
        # same words count.
        if min(words[a][0], words[b][0]) < SHORT_WORDS and words[a][1] != words[b][1]:
            return False
        # Two PDFs must also look the same: different drawings can share all their text.
        pdf = {files[a].path.suffix.lower(), files[b].path.suffix.lower()} == {".pdf"}
        return not pdf or pages_look_alike(look(a), look(b))

    checked, pairs = set(), []
    for members in buckets.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if (a, b) in checked:
                    continue
                checked.add((a, b))
                if same_document(a, b):
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
