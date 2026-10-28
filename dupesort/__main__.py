"""Start the DupeSort desktop app: ``python -m dupesort``."""

import sys
import warnings

# macOS's bundled Python uses LibreSSL; urllib3 warns about it but works fine.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")


def main() -> int:
    if "--check" in sys.argv:  # report which optional helpers were found
        from .tools import find_tool

        for name in ("fpcalc", "ffmpeg", "ffprobe"):
            print(f"{name}: {find_tool(name) or 'not found'}")
        return 0

    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    from pathlib import Path

    from PySide6.QtGui import QIcon

    here = Path(__file__).resolve().parent
    for icon in (here / "icon.png", here.parent / "packaging" / "icon.png"):
        if icon.is_file():  # bundled copy in builds, packaging/ when run from source
            app.setWindowIcon(QIcon(str(icon)))
            break
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
