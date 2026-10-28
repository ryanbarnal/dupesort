import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from dupesort import documents, photos
from dupesort.core.scanner import scan
from dupesort.settings import Settings
from dupesort.videos import parse_name


def picture(seed: int) -> Image.Image:
    img = Image.new("RGB", (800, 600), "white")
    d = ImageDraw.Draw(img)
    for i in range(12):
        x = (seed * 97 + i * 131) % 700
        y = (seed * 53 + i * 71) % 500
        d.ellipse([x, y, x + 60 + i * 5, y + 40 + i * 3], fill=((seed * 40 + i * 20) % 255, 80, 160))
    d.rectangle([seed * 30 % 400, 300, seed * 30 % 400 + 300, 560], fill=(20, 120 + seed, 40))
    return img


def test_similar_photos_grouped(tmp_path):
    original = picture(1)
    exif = Image.Exif()
    exif.get_ifd(photos.EXIF_IFD)[photos.DATE_TAKEN] = "2019:07:04 12:30:00"
    original.save(tmp_path / "original.jpg", quality=95, exif=exif)
    original.resize((400, 300)).save(tmp_path / "small copy.jpg", quality=60)
    original.save(tmp_path / "copy.png")
    picture(7).save(tmp_path / "different.jpg")

    files = scan([tmp_path], "photos")
    groups = photos.find_duplicates(files, Settings(photo_threshold=6))
    assert len(groups) == 1
    assert sorted(f.path.name for f in groups[0].files) == ["copy.png", "original.jpg",
                                                            "small copy.jpg"]
    by = {f.path.name: f for f in files}
    assert by["original.jpg"].info["date"] == datetime(2019, 7, 4, 12, 30)
    # Full-size copy with EXIF beats the resized one.
    assert photos.quality(by["original.jpg"]) > photos.quality(by["small copy.jpg"])


def test_parse_video_names():
    assert parse_name(Path("The.Office.US.S02E05.720p.mkv")) == \
        {"kind": "tv", "title": "The Office US", "season": 2, "episode": 5}
    assert parse_name(Path("friends 3x07.avi"))["episode"] == 7
    assert parse_name(Path("Blade.Runner.1982.Final.Cut.1080p.BluRay.x264.mkv")) == \
        {"kind": "movie", "title": "Blade Runner", "year": 1982}
    assert parse_name(Path("Inception (2010).mp4"))["title"] == "Inception"
    assert parse_name(Path("Holiday video.mov")) == {"kind": "movie", "title": "Holiday video"}


TEXT = " ".join(f"The quarterly report section {i} describes revenue growth in region {i % 7} "
                f"and outlines the plan for hiring and expansion." for i in range(40))


def make_docx(path: Path, text: str) -> None:
    body = "".join(f"<w:p><w:r><w:t>{s}.</w:t></w:r></w:p>" for s in text.split("."))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document><w:body>{body}</w:body></w:document>")


def test_same_text_in_different_formats(tmp_path):
    (tmp_path / "report.txt").write_text(TEXT)
    make_docx(tmp_path / "report.docx", TEXT.replace("region 3", "region 33", 1))
    (tmp_path / "other.txt").write_text(" ".join(reversed(TEXT.split())) + " unrelated words")
    files = scan([tmp_path], "documents")
    assert "quarterly report" in documents.extract_text(tmp_path / "report.docx")
    groups = documents.find_duplicates(files, Settings(document_similarity=85))
    assert [sorted(f.path.name for f in g.files) for g in groups] == [["report.docx", "report.txt"]]


def test_type_folders(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "Word").mkdir()
    (tmp_path / "Word" / "b.docx").write_bytes(b"x")
    moves = documents.plan_type_moves(scan([tmp_path], "documents"))
    assert [(f.path.name, t.parent.name) for f, t in moves] == [("a.pdf", "PDF")]
