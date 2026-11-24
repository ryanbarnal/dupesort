"""Convert tabs: pick files, choose options, convert. Originals are never changed."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QRadioButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ..convert import audio, images, pdf, upscale, video
from ..convert.ffmpeg import ConversionError
from ..core.scanner import CATEGORY_EXTENSIONS
from ..tools import find_tool
from . import icons
from .widgets import human_size


class FileList(QListWidget):
    """A list of input files that also accepts files dropped from the desktop."""

    def __init__(self, exts: set[str]) -> None:
        super().__init__()
        self.exts = exts
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def paths(self) -> list[Path]:
        return [Path(self.item(i).text()) for i in range(self.count())]

    def add(self, paths) -> None:
        have = set(map(str, self.paths()))
        for p in paths:
            p = Path(p)
            if p.is_dir():
                self.add(sorted(c for c in p.rglob("*") if c.is_file()))
            elif p.suffix.lower() in self.exts and str(p) not in have:
                self.addItem(str(p))
                have.add(str(p))

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e) -> None:
        self.add(u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile())


class ConvertTab(QWidget):
    exts: set[str] = set()
    button_text = "Convert"

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.settings = page, page.settings
        self.last_outputs: list[Path] = []

        self.files = FileList(self.input_exts())
        self.files.setToolTip("Drag files or folders here")
        add_files, add_folder = QPushButton("Add files…"), QPushButton("Add folder…")
        use_scan, remove, clear = (QPushButton("Add scanned files"), QPushButton("Remove"),
                                   QPushButton("Clear"))
        for b, kind in ((add_files, "file-plus"), (add_folder, "folder-plus"), (use_scan, "scan"),
                        (remove, "minus"), (clear, "trash")):
            icons.attach(b, kind)
            b.setStyleSheet("text-align: left")
        add_files.clicked.connect(self._add_files)
        add_folder.clicked.connect(self._add_folder)
        use_scan.clicked.connect(lambda: self.files.add(f.path for f in self.page.files))
        remove.clicked.connect(lambda: [self.files.takeItem(self.files.row(i))
                                        for i in self.files.selectedItems()])
        clear.clicked.connect(self.files.clear)
        btns = QVBoxLayout()
        for b in (add_files, add_folder, use_scan, remove, clear):
            btns.addWidget(b)
        btns.addStretch()
        src_box = QGroupBox("Files to convert (drag && drop works too)")
        sl = QHBoxLayout(src_box)
        sl.addWidget(self.files, 1)
        sl.addLayout(btns)

        self.form = QFormLayout()
        self.build_options(self.form)
        opt_box = QGroupBox("Options")
        opt_box.setLayout(self.form)

        self.beside = QRadioButton("Next to the originals")
        self.to_folder = QRadioButton("In this folder:")
        self.beside.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.beside)
        group.addButton(self.to_folder)
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Choose a folder…")
        browse = icons.attach(QPushButton(), "folder")
        browse.setToolTip("Choose a folder")
        browse.clicked.connect(self._pick_folder)
        out_row = QHBoxLayout()
        out_row.addWidget(self.beside)
        out_row.addWidget(self.to_folder)
        out_row.addWidget(self.folder, 1)
        out_row.addWidget(browse)
        out_box = QGroupBox("Save converted files")
        out_box.setLayout(out_row)

        self.summary = QLabel(self.hint())
        self.summary.setWordWrap(True)
        self.open_btn = QPushButton("Show results")
        self.open_btn.setEnabled(False)
        icons.attach(self.open_btn, "open")
        self.open_btn.clicked.connect(self._show_results)
        self.go = QPushButton(self.button_text)
        self.go.setDefault(True)
        icons.attach(self.go, "convert")
        self.go.clicked.connect(self.start)
        page._busy_widgets.append(self.go)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.open_btn)
        bottom.addWidget(self.go)

        top = QHBoxLayout()
        top.addWidget(src_box, 3)
        top.addWidget(opt_box, 2)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addWidget(out_box)
        lay.addLayout(bottom)

    # hooks
    def export_state(self) -> dict:
        return {"files": [str(x) for x in self.files.paths()],
                "to_folder": self.to_folder.isChecked(), "folder": self.folder.text()}

    def restore_state(self, data: dict) -> None:
        self.files.clear()
        self.files.add(Path(x) for x in data.get("files", []) if Path(x).is_file())
        self.folder.setText(data.get("folder", ""))
        (self.to_folder if data.get("to_folder") else self.beside).setChecked(True)

    def input_exts(self) -> set[str]:
        return self.exts

    def build_options(self, form: QFormLayout) -> None:
        pass

    def hint(self) -> str:
        return "Your original files are never changed - converted copies are saved separately."

    def read_options(self, out_dir: Optional[Path]):
        """Collect widget values on the UI thread."""
        raise NotImplementedError

    def convert_one(self, path: Path, opts, frac, cancelled) -> list[Path]:
        raise NotImplementedError

    def preflight(self) -> bool:
        return True

    # shared flow
    def _add_files(self) -> None:
        pattern = " ".join(f"*{e}" for e in sorted(self.files.exts))
        names, _ = QFileDialog.getOpenFileNames(self, "Add files", "", f"Supported ({pattern})")
        self.files.add(names)

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Add every supported file in a folder")
        if d:
            self.files.add([d])

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Save converted files in…")
        if d:
            self.folder.setText(d)
            self.to_folder.setChecked(True)

    def out_dir(self) -> Optional[Path]:
        if self.to_folder.isChecked():
            if not self.folder.text().strip():
                raise ValueError("Choose the folder to save converted files in.")
            return Path(self.folder.text().strip())
        return None

    def start(self) -> None:
        files = self.files.paths()
        if not files:
            QMessageBox.information(self, "No files", "Add some files to convert first.")
            return
        try:
            opts = self.read_options(self.out_dir())
        except ValueError as exc:
            QMessageBox.warning(self, "Convert", str(exc))
            return
        if not self.preflight():
            return

        def job(t):
            outputs, errors, steps = [], [], 1000
            for n, path in enumerate(files):
                if t.cancelled():
                    break

                def frac(f, n=n, name=path.name):
                    t.progress(int((n + max(0.0, min(1.0, f))) * steps), len(files) * steps,
                               f"Converting {name} ({n + 1}/{len(files)})")

                frac(0)
                try:
                    outputs += self.convert_one(path, opts, frac, t.cancelled)
                except (ConversionError, OSError, ValueError) as exc:
                    if str(exc) != "Cancelled":
                        errors.append(f"{path.name}: {exc}")
                except Exception as exc:  # unusual files shouldn't stop the batch
                    errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            return files, outputs, errors

        self.page.run_task("Converting…", job, self._done)

    def _done(self, result) -> None:
        files, outputs, errors = result
        self.last_outputs = outputs
        before = sum(p.stat().st_size for p in files if p.exists())
        after = sum(p.stat().st_size for p in outputs if p.exists())
        text = f"Created {len(outputs)} file{'s' * (len(outputs) != 1)}"
        if outputs and before:
            text += f" · {human_size(before)} → {human_size(after)}"
        if errors:
            text += f" · {len(errors)} failed"
        self.summary.setText(text + ".")
        self.page.status.setText(text + ".")
        self.open_btn.setEnabled(bool(outputs))
        if errors:
            QMessageBox.warning(self, "Some files were not converted", "\n".join(errors[:30]))

    def _show_results(self) -> None:
        if self.last_outputs:
            from .widgets import reveal

            reveal(self.last_outputs[0])


def _combo(items, current=None) -> QComboBox:
    c = QComboBox()
    c.addItems(list(items))
    if current is not None:
        c.setCurrentText(str(current))
    return c


def _ffmpeg_notice(form: QFormLayout) -> None:
    if not find_tool("ffmpeg"):
        warn = QLabel("<b>FFmpeg is not installed</b> - conversion is unavailable. "
                      "See Help → User Guide.")
        warn.setWordWrap(True)
        form.addRow(warn)


class AudioConvertTab(ConvertTab):
    exts = CATEGORY_EXTENSIONS["music"]
    button_text = "Convert songs"

    def build_options(self, form: QFormLayout) -> None:
        _ffmpeg_notice(form)
        self.fmt = _combo(audio.FORMATS, "MP3")
        self.bitrate = _combo([f"{b} kbps" for b in audio.BITRATES], "192 kbps")
        self.no_up = QCheckBox("Never raise the bitrate above the original")
        self.no_up.setChecked(True)
        self.no_up.setToolTip("Re-encoding a 128 kbps file at 320 kbps only makes it bigger - "
                              "quality can't be restored.")
        self.rate = _combo(["Keep", "44100 Hz (CD)", "48000 Hz"], "Keep")
        self.mono = QCheckBox("Convert to mono (half the size; for speech/podcasts)")
        self.fmt.currentTextChanged.connect(
            lambda f: self.bitrate.setEnabled(audio.FORMATS[f][2]))
        form.addRow("Format:", self.fmt)
        form.addRow("Bitrate:", self.bitrate)
        form.addRow("", self.no_up)
        form.addRow("Sample rate:", self.rate)
        form.addRow("", self.mono)
        form.addRow(QLabel("<small>Tags, lyrics and cover art are copied to the new file."
                           "</small>"))

    def read_options(self, out_dir):
        rate = {"Keep": 0, "44100 Hz (CD)": 44100, "48000 Hz": 48000}[self.rate.currentText()]
        return audio.AudioOptions(self.fmt.currentText(),
                                  int(self.bitrate.currentText().split()[0]),
                                  self.no_up.isChecked(), rate, self.mono.isChecked(), out_dir)

    def convert_one(self, path, opts, frac, cancelled):
        return [audio.convert_audio(path, opts, frac, cancelled)]


class ImageConvertTab(ConvertTab):
    exts = CATEGORY_EXTENSIONS["photos"]
    button_text = "Convert photos"

    def build_options(self, form: QFormLayout) -> None:
        self.fmt = _combo(images.FORMATS, "JPEG")
        self.resize = _combo(images.RESIZE_MODES, "Keep size")
        self.percent = QSpinBox()
        self.percent.setRange(5, 400)
        self.percent.setSuffix(" %")
        self.percent.setValue(50)
        self.max_side = QSpinBox()
        self.max_side.setRange(64, 20000)
        self.max_side.setSuffix(" px")
        self.max_side.setValue(2048)
        self.quality = QSlider(Qt.Horizontal)
        self.quality.setRange(30, 100)
        self.quality.setValue(85)
        self.q_label = QLabel()
        self.quality.valueChanged.connect(lambda v: self.q_label.setText(
            f"{v}  ({'best' if v >= 92 else 'high' if v >= 80 else 'smaller file'})"))
        self.quality.valueChanged.emit(85)
        q_row = QHBoxLayout()
        q_row.addWidget(self.quality, 1)
        q_row.addWidget(self.q_label)
        self.reduce = QCheckBox("Reduce PNG colours (much smaller, for graphics/screenshots)")
        self.strip = QCheckBox("Remove camera && GPS location data")

        def sync(*_):
            mode = self.resize.currentText()
            self.percent.setEnabled(mode == "Scale by percent")
            self.max_side.setEnabled(mode == "Fit within (pixels)")
            fmt = self.fmt.currentText()
            self.quality.setEnabled(fmt in ("JPEG", "WebP", "Keep format"))
            self.reduce.setEnabled(fmt in ("PNG", "Keep format"))

        self.resize.currentTextChanged.connect(sync)
        self.fmt.currentTextChanged.connect(sync)
        sync()
        form.addRow("Save as:", self.fmt)
        form.addRow("Size:", self.resize)
        form.addRow("Percent:", self.percent)
        form.addRow("Longest side:", self.max_side)
        form.addRow("Quality:", q_row)
        form.addRow("", self.reduce)
        form.addRow("", self.strip)
        form.addRow(QLabel("<small>“Simple” upscaling is instant. “AI” upscaling adds real "
                           "detail using Real-ESRGAN (downloaded on first use).</small>",
                           wordWrap=True))

    def read_options(self, out_dir):
        return images.ImageOptions(self.fmt.currentText(), self.resize.currentText(),
                                   self.percent.value(), self.max_side.value(),
                                   self.quality.value(), self.reduce.isChecked(),
                                   self.strip.isChecked(), out_dir)

    def preflight(self) -> bool:
        if "(AI)" not in self.resize.currentText() or upscale.installed():
            return True
        answer = QMessageBox.question(
            self, "Download AI upscaler",
            f"AI upscaling uses Real-ESRGAN, a free open-source upscaler (about "
            f"{upscale.download_size_mb()} MB).\n\nDownload it now from "
            "github.com/xinntao/Real-ESRGAN? It is saved in DupeSort's app folder and "
            "only downloaded once.")
        if answer != QMessageBox.Yes:
            return False

        def job(t):
            upscale.install(lambda done, total: t.progress(
                done, total, f"Downloading AI upscaler… {done // 1048576} MB"))

        self.page.run_task("Downloading AI upscaler…", job, lambda _: self.start())
        return False  # start() runs again once the download finishes

    def convert_one(self, path, opts, frac, cancelled):
        out = images.convert_image(path, opts)
        frac(1)
        return [out]


class VideoConvertTab(ConvertTab):
    exts = CATEGORY_EXTENSIONS["videos"]
    button_text = "Convert videos"

    def build_options(self, form: QFormLayout) -> None:
        _ffmpeg_notice(form)
        self.container = _combo(video.CONTAINERS, "MP4")
        self.codec = _combo(video.CODECS)
        self.res = _combo(video.RESOLUTIONS, "Keep")
        self.aspect = _combo(video.ASPECTS, "Keep")
        self.mode = _combo(video.ASPECT_MODES)
        self.quality = _combo(video.QUALITY, "Balanced")

        def sync(*_):
            c = self.container.currentText()
            self.codec.setEnabled(c in ("MP4", "MOV", "MKV", "WebM"))
            self.mode.setEnabled(self.aspect.currentText() != "Keep")

        self.container.currentTextChanged.connect(sync)
        self.aspect.currentTextChanged.connect(sync)
        sync()
        form.addRow("Format:", self.container)
        form.addRow("Video codec:", self.codec)
        form.addRow("Resolution:", self.res)
        form.addRow("Aspect ratio:", self.aspect)
        form.addRow("Fit mode:", self.mode)
        form.addRow("Quality / size:", self.quality)
        form.addRow(QLabel("<small>WebM uses VP9/AV1 and AVI uses MPEG-4 automatically. "
                           "“Small file” is ideal for sharing and messaging.</small>",
                           wordWrap=True))

    def read_options(self, out_dir):
        return video.VideoOptions(self.container.currentText(), self.codec.currentText(),
                                  self.res.currentText(), self.aspect.currentText(),
                                  self.mode.currentText(), self.quality.currentText(), out_dir)

    def convert_one(self, path, opts, frac, cancelled):
        return [video.convert_video(path, opts, frac, cancelled)]


PDF_OPS = ("Images → PDF", "PDF → images", "Word / Excel / PowerPoint → PDF",
           "PDF → text", "Merge PDFs into one", "Compress PDFs (smaller size)")


class PdfTab(ConvertTab):
    button_text = "Run"

    def input_exts(self) -> set[str]:
        return {".pdf"} | pdf.OFFICE_EXTS | pdf.IMAGE_EXTS

    def build_options(self, form: QFormLayout) -> None:
        self.op = _combo(PDF_OPS)
        self.page_size = _combo(pdf.PAGE_SIZES)
        self.img_fmt = _combo(["PNG", "JPEG"])
        self.dpi = _combo(["72", "150", "300"], "150")
        self.quality = QSpinBox()
        self.quality.setRange(20, 95)
        self.quality.setValue(60)
        self.quality.setToolTip("JPEG quality for pictures inside the PDF. Lower = smaller.")
        self.office_note = QLabel(wordWrap=True)

        def sync(*_):
            op = self.op.currentText()
            self.page_size.setEnabled(op == PDF_OPS[0])
            self.img_fmt.setEnabled(op == PDF_OPS[1])
            self.dpi.setEnabled(op in PDF_OPS[:2])
            self.quality.setEnabled(op == PDF_OPS[5])
            if op == PDF_OPS[2]:
                tool = pdf.office_available()
                self.office_note.setText(
                    f"<small>Using {tool}.</small>" if tool else
                    "<small><b>Needs the free LibreOffice</b> (libreoffice.org)"
                    f"{' or Microsoft Office' if os.name == 'nt' else ''}.</small>")
            else:
                self.office_note.setText("")
            self.go.setText({PDF_OPS[0]: "Make PDF", PDF_OPS[4]: "Merge"}.get(op, "Convert"))

        self.op.currentTextChanged.connect(sync)
        form.addRow("Task:", self.op)
        form.addRow("Page size:", self.page_size)
        form.addRow("Image format:", self.img_fmt)
        form.addRow("Resolution (dpi):", self.dpi)
        form.addRow("Picture quality:", self.quality)
        form.addRow(self.office_note)
        self._sync = sync

    def showEvent(self, e) -> None:  # the Convert button exists once built
        self._sync()
        super().showEvent(e)

    def hint(self) -> str:
        return ("Pick a task, add files (images, PDFs or Office documents) and press the "
                "button. Originals are never changed.")

    def read_options(self, out_dir):
        op = self.op.currentText()
        files = self.files.paths()
        wanted = {PDF_OPS[0]: pdf.IMAGE_EXTS, PDF_OPS[2]: pdf.OFFICE_EXTS}.get(op, {".pdf"})
        usable = [p for p in files if p.suffix.lower() in wanted]
        if not usable:
            raise ValueError(f"None of the files suit “{op}”. Add "
                             + {PDF_OPS[0]: "images", PDF_OPS[2]: "Word, Excel or "
                                "PowerPoint files"}.get(op, "PDF files") + ".")
        if op == PDF_OPS[2] and not pdf.office_available():
            raise ValueError("Converting Office documents needs the free LibreOffice "
                             "(libreoffice.org). Install it and try again.")
        target = None
        if op in (PDF_OPS[0], PDF_OPS[4]):
            default = (out_dir or usable[0].parent) / ("Combined.pdf" if op == PDF_OPS[4]
                                                       else f"{usable[0].stem} album.pdf")
            name, _ = QFileDialog.getSaveFileName(self, "Save PDF as", str(default), "PDF (*.pdf)")
            if not name:
                raise ValueError("No file name chosen.")
            target = Path(name if name.lower().endswith(".pdf") else name + ".pdf")
        return {"op": op, "usable": usable, "out_dir": out_dir, "target": target,
                "page": self.page_size.currentText(), "fmt": self.img_fmt.currentText(),
                "dpi": int(self.dpi.currentText()), "quality": self.quality.value()}

    def start(self) -> None:
        # Single-output tasks process every file in one step.
        self._ran_combined = False
        super().start()

    def convert_one(self, path, o, frac, cancelled):
        if path not in o["usable"]:
            return []
        op = o["op"]
        if op in (PDF_OPS[0], PDF_OPS[4]):
            if self._ran_combined:
                return []
            self._ran_combined = True
            prog = lambda n, total: frac(n / total)  # noqa: E731
            if op == PDF_OPS[0]:
                return [pdf.images_to_pdf(o["usable"], o["target"], o["page"], o["dpi"],
                                          progress=prog)]
            return [pdf.merge_pdfs(o["usable"], o["target"], progress=prog)]
        if op == PDF_OPS[1]:
            return pdf.pdf_to_images(path, o["out_dir"] or path.parent, o["fmt"], o["dpi"],
                                     progress=lambda n, total: frac(n / total),
                                     cancelled=cancelled)
        if op == PDF_OPS[2]:
            return [pdf.office_to_pdf(path, o["out_dir"])]
        if op == PDF_OPS[3]:
            return [pdf.pdf_to_text(path, o["out_dir"])]
        return [pdf.compress_pdf(path, o["out_dir"], o["quality"])[0]]
