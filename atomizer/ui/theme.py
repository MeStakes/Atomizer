"""Neon cyber/sci-fi theme: palette constants + Qt stylesheet (QSS).

Near-black backgrounds with electric-cyan / magenta-violet / aqua-green accents,
rounded corners, subtle borders, and glow on active elements.
"""

from __future__ import annotations

# --- Palette ---------------------------------------------------------------
BG_DEEP = "#0A0E14"
BG_PANEL = "#12161F"
BG_RAISED = "#1A1F2B"
BG_INPUT = "#0E131C"
BORDER = "#243040"
BORDER_HI = "#2E3C50"

CYAN = "#00E5FF"
VIOLET = "#B14EFF"
AQUA = "#00FFC6"
DANGER = "#FF4E6A"

TEXT = "#E6F0F5"
TEXT_MUTED = "#7A8694"

# Font stack: geometric/tech sans, graceful fallback if Orbitron absent.
LOGO_FONT = "'Orbitron', 'Space Grotesk', 'SF Pro Display', 'Helvetica Neue', sans-serif"
UI_FONT = "'Space Grotesk', 'Inter', 'SF Pro Text', 'Helvetica Neue', sans-serif"
MONO_FONT = "'JetBrains Mono', 'SF Mono', 'Menlo', monospace"


QSS = f"""
* {{
    font-family: {UI_FONT};
    color: {TEXT};
    outline: none;
}}

QMainWindow, QWidget#Root {{
    background-color: {BG_DEEP};
}}

QWidget#Card {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}

QLabel#SectionTitle {{
    color: {CYAN};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
}}

QLabel#Hint, QLabel#Muted {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QLabel#ModelDesc {{
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 2px 0;
}}

/* --- Inputs --- */
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 12px;
    selection-background-color: {VIOLET};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {CYAN};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}

QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {CYAN};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_RAISED};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    selection-background-color: {VIOLET};
    selection-color: #ffffff;
    padding: 4px;
}}

/* --- Drop zone --- */
QFrame#DropZone {{
    background-color: {BG_INPUT};
    border: 1.5px dashed {BORDER_HI};
    border-radius: 14px;
}}
QFrame#DropZone[dragActive="true"] {{
    border: 1.5px dashed {CYAN};
    background-color: #0c1a22;
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {BG_RAISED};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 600;
}}
QPushButton:hover {{
    border: 1px solid {CYAN};
    color: {CYAN};
}}
QPushButton:pressed {{
    background-color: #0c1a22;
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border: 1px solid {BORDER};
}}

QPushButton#Primary {{
    background-color: {CYAN};
    color: #04161a;
    border: none;
    border-radius: 12px;
    padding: 14px 22px;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 3px;
}}
QPushButton#Primary:hover {{
    background-color: #4af1ff;
}}
QPushButton#Primary:disabled {{
    background-color: {BG_RAISED};
    color: {TEXT_MUTED};
}}

QPushButton#Ghost {{
    background-color: transparent;
    border: 1px solid {BORDER_HI};
    padding: 6px 12px;
}}

QPushButton#Play {{
    background-color: transparent;
    border: 1px solid {VIOLET};
    color: {VIOLET};
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}}
QPushButton#Play:hover {{
    background-color: rgba(177, 78, 255, 0.12);
}}

/* --- Checkboxes --- */
QCheckBox {{
    spacing: 8px;
    padding: 4px 0;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {BORDER_HI};
    background-color: {BG_INPUT};
}}
QCheckBox::indicator:hover {{
    border: 1px solid {CYAN};
}}
QCheckBox::indicator:checked {{
    background-color: {CYAN};
    border: 1px solid {CYAN};
}}

/* --- Progress --- */
QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 9px;
    height: 18px;
    text-align: center;
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QProgressBar::chunk {{
    border-radius: 8px;
    background-color: {CYAN};
}}

/* --- Status log --- */
QPlainTextEdit#Log {{
    font-family: {MONO_FONT};
    font-size: 12px;
    color: #b9ffe9;
    background-color: #080c12;
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

/* --- BPM / Key chips --- */
QLabel#MetricValue {{
    font-family: {LOGO_FONT};
    font-size: 30px;
    font-weight: 800;
    color: {TEXT};
}}
QLabel#MetricLabel {{
    color: {TEXT_MUTED};
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QLabel#SourceBadge {{
    color: {AQUA};
    font-size: 11px;
    font-weight: 600;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_HI};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
