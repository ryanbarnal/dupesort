"""Light / dark / system appearance and accent colour themes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

MODES = ("System", "Light", "Dark")
# Sky and Pink are the two colours of the Twin Circles logo.
ACCENTS = {
    "Sky": "#0ea5e9",
    "Pink": "#ec4899",
    "Indigo": "#6366f1",
    "Teal": "#14b8a6",
    "Green": "#22c55e",
    "Orange": "#f97316",
    "Purple": "#a855f7",
    "Slate": "#64748b",
}

_LIGHT = {"window": "#f5f6f8", "base": "#ffffff", "alt": "#eef0f4", "text": "#1d2129",
          "muted": "#6b7280", "button": "#ffffff", "border": "#d5d9e0", "sidebar": "#eceef2"}
_DARK = {"window": "#16181d", "base": "#1e2128", "alt": "#252932", "text": "#e6e8ec",
         "muted": "#9aa1ad", "button": "#2a2e37", "border": "#3a3f4a", "sidebar": "#111317"}


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt older than 6.5
        return QApplication.palette().window().color().lightness() < 128


def is_dark(mode: str) -> bool:
    return mode == "Dark" or (mode == "System" and system_is_dark())


def apply(mode: str = "System", accent: str = "Sky") -> None:
    app = QApplication.instance()
    dark = is_dark(mode)
    c = _DARK if dark else _LIGHT
    acc = QColor(ACCENTS.get(accent, ACCENTS["Sky"]))
    app.setStyle("Fusion")

    pal = QPalette()
    roles = {
        QPalette.Window: c["window"], QPalette.WindowText: c["text"], QPalette.Base: c["base"],
        QPalette.AlternateBase: c["alt"], QPalette.Text: c["text"], QPalette.Button: c["button"],
        QPalette.ButtonText: c["text"], QPalette.ToolTipBase: c["base"],
        QPalette.ToolTipText: c["text"], QPalette.PlaceholderText: c["muted"],
        QPalette.BrightText: "#ffffff", QPalette.Mid: c["border"], QPalette.Dark: c["border"],
        QPalette.Light: c["base"], QPalette.Midlight: c["alt"], QPalette.Shadow: "#000000",
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    pal.setColor(QPalette.Highlight, acc)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.Link, acc.lighter(130) if dark else acc.darker(110))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    app.setPalette(pal)

    hover = acc.lighter(115).name()
    app.setStyleSheet(f"""
        QPushButton {{ padding: 5px 14px; border-radius: 6px; border: 1px solid {c['border']};
                       background: {c['button']}; }}
        QPushButton:hover {{ border-color: {acc.name()}; }}
        QPushButton:default {{ background: {acc.name()}; color: white; border: none; }}
        QPushButton:default:hover {{ background: {hover}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['alt']}; }}
        QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 10px;
                     padding-top: 6px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
        QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 6px; top: -1px; }}
        QTabBar::tab {{ padding: 6px 14px; border: 1px solid transparent; }}
        QTabBar::tab:selected {{ border-bottom: 2px solid {acc.name()}; font-weight: bold; }}
        QProgressBar {{ border: 1px solid {c['border']}; border-radius: 5px; text-align: center;
                        height: 14px; }}
        QProgressBar::chunk {{ background: {acc.name()}; border-radius: 4px; }}
        QListWidget#nav {{ background: {c['sidebar']}; border: none; padding: 6px;
                           font-size: 14px; outline: 0; }}
        QListWidget#nav::item {{ padding: 8px 10px; border-radius: 8px; margin: 2px 0; }}
        QListWidget#nav::item:selected {{ background: {acc.name()}; color: white; }}
        QListWidget#nav::item:hover:!selected {{ background: {c['alt']}; }}
        QWidget#sidebar {{ background: {c['sidebar']}; }}
        QLabel#notice {{ background: {c['alt']}; padding: 6px; border-radius: 6px; }}
    """)
