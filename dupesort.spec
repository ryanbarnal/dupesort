# PyInstaller build recipe:  pyinstaller dupesort.spec
# Optional helpers placed in ./bin (fpcalc, ffmpeg, ffprobe - .exe on Windows)
# are bundled so users need not install them separately.
# Installers are made from the result by packaging/build_macos.sh (DMG) and
# packaging/windows/dupesort.iss (Inno Setup).
import re
import sys
from pathlib import Path

VERSION = re.search(r'__version__ = "([^"]+)"', Path("dupesort/__init__.py").read_text()).group(1)
ICON = {"darwin": "packaging/icon.icns", "win32": "packaging/icon.ico"}.get(sys.platform)

helpers = [(str(p), "bin") for p in Path("bin").glob("*") if p.is_file()] if Path("bin").is_dir() else []

a = Analysis(
    ["run_dupesort.py"],
    binaries=helpers,
    datas=[("dupesort/gui/logo.png", "dupesort/gui"), ("dupesort/gui/guide.html", "dupesort/gui")],
    hiddenimports=["pillow_heif", "pypdfium2"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DupeSort",
          console=False, upx=False, icon=ICON)
coll = COLLECT(exe, a.binaries, a.datas, name="DupeSort", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(coll, name="DupeSort.app", icon=ICON, bundle_identifier="org.dupesort.app",
                 version=VERSION,
                 info_plist={"NSHighResolutionCapable": True,
                             "CFBundleShortVersionString": VERSION,
                             "CFBundleVersion": VERSION,
                             "LSMinimumSystemVersion": "13.0",
                             "NSHumanReadableCopyright": "DupeSort"})
