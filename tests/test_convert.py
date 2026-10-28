from pathlib import Path

import pytest
from conftest import make_wav
from PIL import Image, ImageDraw

from dupesort.convert import audio, images, pdf, video
from dupesort.convert.ffmpeg import probe
from dupesort.music.tags import audio_info, read_cover, read_tags, write_tags
from dupesort.tools import find_tool

needs_ffmpeg = pytest.mark.skipif(not (find_tool("ffmpeg") and find_tool("ffprobe")),
                                  reason="FFmpeg not installed")


def photo(path: Path, size=(400, 300)) -> Path:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(0, size[0], 20):
        d.line([(i, 0), (size[0] - i, size[1])], fill=(i % 255, 90, 200), width=3)
    img.save(path)
    return path


@needs_ffmpeg
def test_audio_convert_keeps_tags_and_cover(tmp_path):
    src = make_wav(tmp_path / "song.wav", seconds=3, rate=44100)
    write_tags(src, {"artist": "Band", "title": "Song", "lyrics": "la la"},
               cover=b"\xff\xd8\xff\xe0" + b"0" * 100)
    out = audio.convert_audio(src, audio.AudioOptions(fmt="MP3", bitrate=128))
    assert out.suffix == ".mp3" and out.exists()
    assert read_tags(out) == {"artist": "Band", "title": "Song", "lyrics": "la la"}
    assert read_cover(out).startswith(b"\xff\xd8")
    assert 100 <= audio_info(out)["bitrate"] // 1000 <= 140
    flac = audio.convert_audio(out, audio.AudioOptions(fmt="FLAC (lossless)",
                                                       out_dir=tmp_path / "flac"))
    assert flac.parent.name == "flac" and read_tags(flac)["title"] == "Song"


@needs_ffmpeg
def test_audio_bitrate_never_raised_above_source(tmp_path):
    src = make_wav(tmp_path / "s.wav", seconds=3, rate=44100)
    low = audio.convert_audio(src, audio.AudioOptions(fmt="MP3", bitrate=96))
    high = audio.convert_audio(low, audio.AudioOptions(fmt="MP3", bitrate=320))
    assert high.name == "s (96k).mp3"  # same format -> a bitrate suffix, no overwrite
    assert audio_info(high)["bitrate"] // 1000 <= 112


def test_image_formats_and_sizes(tmp_path):
    src = photo(tmp_path / "pic.png")
    jpg = images.convert_image(src, images.ImageOptions(fmt="JPEG", quality=70))
    assert jpg.suffix == ".jpg" and Image.open(jpg).format == "JPEG"
    big = images.convert_image(src, images.ImageOptions(fmt="PNG", resize="Upscale 2× (simple)",
                                                        out_dir=tmp_path / "big"))
    assert Image.open(big).size == (800, 600)
    small = images.convert_image(src, images.ImageOptions(fmt="Keep format",
                                                          resize="Fit within (pixels)",
                                                          max_side=100, png_reduce_colors=True))
    assert Image.open(small).size == (100, 75)
    assert small.stat().st_size < src.stat().st_size
    assert small.name == "pic (converted).png"


def test_jpeg_from_transparent_png_and_exif_rotation(tmp_path):
    rgba = Image.new("RGBA", (50, 20), (255, 0, 0, 0))
    rgba.save(tmp_path / "t.png")
    out = images.convert_image(tmp_path / "t.png", images.ImageOptions(fmt="JPEG"))
    assert Image.open(out).getpixel((5, 5)) == (255, 255, 255)  # transparent -> white

    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90°"
    Image.new("RGB", (60, 30), "blue").save(tmp_path / "r.jpg", exif=exif)
    out = images.convert_image(tmp_path / "r.jpg", images.ImageOptions(fmt="PNG"))
    im = Image.open(out)
    assert im.size == (30, 60) and im.getexif().get(0x0112, 1) == 1


@needs_ffmpeg
@pytest.mark.parametrize("aspect,mode,size", [
    ("1:1 (square)", "Fill (crop edges)", (360, 360)),
    ("9:16 (vertical / Reels)", "Fit (add black bars)", (360, 640)),
    ("Keep", "Fit (add black bars)", (640, 360)),
])
def test_video_resize_and_aspect(tmp_path, aspect, mode, size):
    import subprocess

    src = tmp_path / "clip.mov"
    subprocess.run([find_tool("ffmpeg"), "-v", "quiet", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=1280x720:rate=25:duration=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-shortest", "-c:v", "mpeg4", str(src)],
                   check=True)
    opts = video.VideoOptions(container="MP4", resolution="360p", aspect=aspect,
                              aspect_mode=mode, quality="Small file")
    seen = []
    out = video.convert_video(src, opts, progress=seen.append)
    streams = probe(out)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == size and v["codec_name"] == "h264"
    assert any(s["codec_type"] == "audio" for s in streams)
    assert seen and seen[-1] == 1.0


def test_target_size():
    assert video.target_size(1920, 1080, 0, (9, 16)) == (1080, 1920)
    assert video.target_size(1080, 1920, 720, None) == (720, 1280)
    assert video.target_size(1920, 1080, 1080, (21, 9)) == (2520, 1080)


def test_pdf_round_trip_merge_text_compress(tmp_path):
    pics = [photo(tmp_path / f"p{i}.jpg", (1200, 900)) for i in range(2)]
    doc = pdf.images_to_pdf(pics, tmp_path / "album.pdf", page="A4")
    pages = pdf.pdf_to_images(doc, tmp_path / "pages", fmt="JPEG", dpi=72)
    w, h = Image.open(pages[0]).size
    assert len(pages) == 2 and w == 842 and abs(h - 595) <= 1  # A4 landscape at 72 dpi

    merged = pdf.merge_pdfs([doc, doc], tmp_path / "merged.pdf")
    assert len(pdf.pdf_to_images(merged, tmp_path / "m", dpi=20)) == 4

    out, old, new = pdf.compress_pdf(doc, image_quality=30, max_image_side=600)
    assert out.name == "album (compressed).pdf" and new < old

    text = pdf.pdf_to_text(doc)
    assert "--- Page 2 ---" in text.read_text()
