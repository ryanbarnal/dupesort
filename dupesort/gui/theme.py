"""Light / dark / system appearance and accent colours.

The look is quiet and monochrome: near-white or near-black surfaces, hairline
1px borders, flat buttons with thin outline icons, and colour only on the one
main button of each screen. "Mono" (the default accent) keeps even that
black-and-white.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QLabel

MODES = ("System", "Light", "Dark")
DEFAULT_ACCENT = "Mono"
# "Mono" follows the text colour (black in light mode, white in dark mode).
ACCENTS = {
    "Mono": None,
    "Sky": "#0ea5e9",
    "Pink": "#ec4899",
    "Indigo": "#6366f1",
    "Teal": "#14b8a6",
    "Green": "#22c55e",
    "Orange": "#f97316",
    "Purple": "#a855f7",
    "Slate": "#64748b",
}

_LIGHT = {"window": "#f4f4f3", "base": "#ffffff", "alt": "#fafaf9", "text": "#111111",
          "muted": "#6e6e6b", "faint": "#a3a3a0", "button": "#ffffff", "border": "#e3e3e1",
          "sidebar": "#ffffff", "hover": "#f0f0ef", "soft": "#ebebea"}
_DARK = {"window": "#0e0e0e", "base": "#161616", "alt": "#1a1a1a", "text": "#ededed",
         "muted": "#8f8f8c", "faint": "#5c5c5a", "button": "#161616", "border": "#2a2a2a",
         "sidebar": "#111111", "hover": "#1f1f1f", "soft": "#262626"}

FONTS = ("Inter", "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue")

_LINK = re.compile(r"<a (?:style='[^']*' )?")

# Colours of the theme in use, for widgets that draw themselves (icons, intro).
current: dict[str, str] = {}


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt older than 6.5
        return QApplication.palette().window().color().lightness() < 128


def is_dark(mode: str) -> bool:
    return mode == "Dark" or (mode == "System" and system_is_dark())


def _ui_font() -> QFont:
    font = QFont(QApplication.font())
    families = set(QFontDatabase.families())
    for name in FONTS:
        if name in families:
            font.setFamily(name)
            break
    return font


def apply(mode: str = "System", accent: str = DEFAULT_ACCENT) -> None:
    app = QApplication.instance()
    dark = is_dark(mode)
    c = dict(_DARK if dark else _LIGHT)
    hex_ = ACCENTS.get(accent)  # None means Mono
    acc = QColor(hex_ or c["text"])
    on_acc = c["base"] if hex_ is None else "#ffffff"
    if hex_ is None:
        hover = "#cfcfcf" if dark else "#333333"
    else:
        hover = acc.lighter(112).name()
    c.update(accent=acc.name(), on_accent=on_acc, accent_hover=hover)
    current.clear()
    current.update(c, dark="1" if dark else "")

    app.setStyle("Fusion")
    app.setFont(_ui_font())

    pal = QPalette()
    roles = {
        QPalette.Window: c["window"], QPalette.WindowText: c["text"], QPalette.Base: c["base"],
        QPalette.AlternateBase: c["alt"], QPalette.Text: c["text"], QPalette.Button: c["button"],
        QPalette.ButtonText: c["text"], QPalette.ToolTipBase: c["base"],
        QPalette.ToolTipText: c["text"], QPalette.PlaceholderText: c["faint"],
        QPalette.BrightText: "#ffffff", QPalette.Mid: c["border"], QPalette.Dark: c["border"],
        QPalette.Light: c["base"], QPalette.Midlight: c["border"], QPalette.Shadow: c["border"],
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    pal.setColor(QPalette.Highlight, acc)
    pal.setColor(QPalette.HighlightedText, QColor(on_acc))
    pal.setColor(QPalette.Link, QColor(c["text"]) if hex_ is None
                 else (acc.lighter(130) if dark else acc.darker(110)))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["faint"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(c))

    from . import icons  # late import: icons reads the palette set above

    icons.refresh_buttons()
    # Labels with links keep the link colour they were created with; redo them.
    link = pal.color(QPalette.Link).name()
    for w in app.allWidgets():
        if isinstance(w, QLabel) and "<a " in w.text():
            w.setText(_LINK.sub(f"<a style='color:{link}' ", w.text()))


def stylesheet(c: dict[str, str]) -> str:
    return f"""
        QWidget {{ outline: 0; }}
        QMainWindow, QDialog {{ background: {c['window']}; }}
        QToolTip {{ background: {c['base']}; color: {c['text']}; border: 1px solid {c['border']};
                    border-radius: 6px; padding: 4px 8px; }}

        /* Buttons: flat, hairline border, thin icon; the main one is filled. */
        QPushButton {{ min-height: 20px; padding: 5px 12px; border-radius: 6px;
                       border: 1px solid {c['border']}; background: {c['button']};
                       color: {c['text']}; }}
        QPushButton:hover {{ background: {c['hover']}; }}
        QPushButton:pressed {{ background: {c['soft']}; }}
        QPushButton:disabled {{ color: {c['faint']}; background: transparent; }}
        QPushButton:default {{ background: {c['accent']}; color: {c['on_accent']};
                               border: 1px solid {c['accent']}; font-weight: 600; }}
        QPushButton:default:hover {{ background: {c['accent_hover']};
                                     border-color: {c['accent_hover']}; }}
        QPushButton:default:disabled {{ background: {c['soft']}; border-color: {c['soft']};
                                        color: {c['faint']}; }}
        QPushButton:checked {{ background: {c['soft']}; }}

        /* Inputs */
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
            background: {c['base']}; border: 1px solid {c['border']}; border-radius: 6px;
            padding: 4px 8px; selection-background-color: {c['soft']};
            selection-color: {c['text']}; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {c['muted']}; }}
        QComboBox::drop-down {{ border: 0; width: 20px; }}
        QComboBox QAbstractItemView {{ background: {c['base']}; border: 1px solid {c['border']};
                                       padding: 4px; }}
        QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button,
        QDoubleSpinBox::down-button {{ border: 0; width: 16px; }}

        /* Sections */
        QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 18px;
                     padding: 10px 8px 8px 8px; background: {c['base']}; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 2px; top: 0px; padding: 0 2px;
                            color: {c['muted']}; }}
        QLabel#notice {{ background: {c['base']}; border: 1px solid {c['border']};
                         padding: 8px 10px; border-radius: 6px; color: {c['muted']}; }}
        QLabel#heading {{ font-size: 22px; font-weight: 600; padding: 0; }}
        QLabel#muted {{ color: {c['muted']}; }}
        QLabel#excerpt {{ background: {c['base']}; border: 1px solid {c['border']};
                          border-radius: 6px; padding: 8px; color: {c['muted']};
                          font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px; }}
        QLabel#fieldLabel {{ color: {c['muted']}; min-width: 52px; }}

        QFrame#updateBar {{ background: {c['base']}; border-bottom: 1px solid {c['border']}; }}

        /* Folder chips */
        QPushButton#chip {{ background: {c['soft']}; border: 1px solid {c['soft']};
                            border-radius: 13px; padding: 3px 8px 3px 12px; min-height: 18px; }}
        QPushButton#chip:hover {{ border-color: {c['faint']}; }}
        QPushButton#chipAdd {{ background: transparent; border: 1px dashed {c['faint']};
                               border-radius: 13px; padding: 3px 12px; min-height: 18px;
                               color: {c['muted']}; }}
        QPushButton#chipAdd:hover {{ color: {c['text']}; border-color: {c['muted']}; }}

        /* Page sections: a compact segmented switch */
        QTabWidget#sections::pane {{ border: 0; top: 0; }}
        QTabBar#segments {{ background: {c['soft']}; border-radius: 8px; }}
        QTabBar#segments::tab {{ margin: 3px 0 3px 3px; padding: 5px 14px; border: 0;
                                 border-radius: 6px; color: {c['muted']}; }}
        QTabBar#segments::tab:last {{ margin-right: 3px; }}
        QTabBar#segments::tab:selected {{ background: {c['base']}; color: {c['text']};
                                          border: 0; }}
        QTabBar#segments::tab:hover:!selected {{ color: {c['text']}; }}

        /* Lists, trees and tables */
        QAbstractItemView {{ background: {c['base']}; alternate-background-color: {c['alt']};
                             border: 1px solid {c['border']}; border-radius: 6px;
                             selection-background-color: {c['soft']};
                             selection-color: {c['text']}; }}
        QAbstractItemView::item {{ padding: 2px 0; }}
        QAbstractItemView::item:hover {{ background: {c['hover']}; }}
        QAbstractItemView::item:selected {{ background: {c['soft']}; color: {c['text']}; }}
        QHeaderView {{ background: {c['base']}; border: 0; }}
        QHeaderView::section {{ background: {c['base']}; color: {c['muted']}; border: 0;
                                border-bottom: 1px solid {c['border']}; padding: 6px 8px; }}
        QTableCornerButton::section {{ background: {c['base']}; border: 0; }}

        /* Sidebar */
        QWidget#sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
        QListWidget#nav {{ background: transparent; border: none; padding: 0; outline: 0; }}
        QListWidget#nav::item {{ padding: 6px 10px; border-radius: 6px; margin: 1px 0;
                                 color: {c['muted']}; }}
        QListWidget#nav::item:hover:!selected {{ background: {c['hover']}; color: {c['text']}; }}
        QListWidget#nav::item:selected {{ background: {c['soft']}; color: {c['text']};
                                          font-weight: 600; }}
        QLabel#brand {{ font-size: 15px; font-weight: 600; }}
        QLabel#version, QLabel#credit {{ color: {c['muted']}; font-size: 11px; }}

        /* Progress: a thin line */
        QProgressBar {{ border: 0; border-radius: 2px; background: {c['soft']};
                        max-height: 4px; min-height: 4px; color: transparent; }}
        QProgressBar::chunk {{ background: {c['accent']}; border-radius: 2px; }}

        /* Thin scrollbars */
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
        QScrollBar::handle {{ background: {c['border']}; border-radius: 3px; min-height: 24px;
                              min-width: 24px; }}
        QScrollBar::handle:hover {{ background: {c['faint']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

        QSplitter::handle {{ background: transparent; }}
        QSplitter::handle:horizontal {{ width: 8px; }}
        QSplitter::handle:vertical {{ height: 8px; }}

        /* Menus and status bar */
        QMenuBar {{ background: {c['window']}; border-bottom: 1px solid {c['border']}; }}
        QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 4px; }}
        QMenuBar::item:selected {{ background: {c['hover']}; }}
        QMenu {{ background: {c['base']}; border: 1px solid {c['border']}; border-radius: 8px;
                 padding: 4px; }}
        QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {c['hover']}; color: {c['text']}; }}
        QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 6px; }}
        QStatusBar {{ background: {c['window']}; color: {c['muted']};
                      border-top: 1px solid {c['border']}; }}
        QStatusBar::item {{ border: 0; }}
        QScrollArea {{ background: transparent; border: 0; }}
        QTextBrowser {{ border: 1px solid {c['border']}; border-radius: 6px; }}
    """
