"""Synthwave neon theme: palette constants + Qt stylesheet (QSS).

Near-black indigo backgrounds with neon violet / hot-pink / deep-indigo accents,
rounded corners, subtle borders, and glow on active elements.
"""

from __future__ import annotations

# --- Palette ---------------------------------------------------------------
BG_DEEP = "#0B0712"
BG_PANEL = "#15101E"
BG_RAISED = "#1C1530"
BG_INPUT = "#0F0A18"
BORDER = "#2A2140"
BORDER_HI = "#3A2D55"

# Semantic neon accents (synthwave).
PRIMARY = "#C04DFF"  # neon violet — primary accent
ACCENT = "#FF4DD8"   # hot pink — secondary accent
DEEP = "#6A2BFF"     # deep indigo
DANGER = "#FF4E6A"

TEXT = "#F0E8F7"
TEXT_MUTED = "#9A8FB0"

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
    color: {PRIMARY};
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
    selection-background-color: {PRIMARY};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {PRIMARY};
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
    border-top: 6px solid {PRIMARY};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_RAISED};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    selection-background-color: {PRIMARY};
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
    border: 1.5px dashed {PRIMARY};
    background-color: #1a0f2b;
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
    border: 1px solid {PRIMARY};
    color: {PRIMARY};
}}
QPushButton:pressed {{
    background-color: #1a0f2b;
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border: 1px solid {BORDER};
}}

QPushButton#Primary {{
    background-color: {PRIMARY};
    color: #1a0524;
    border: none;
    border-radius: 12px;
    padding: 14px 22px;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 3px;
}}
QPushButton#Primary:hover {{
    background-color: #D26BFF;
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
    border: 1px solid {PRIMARY};
    color: {PRIMARY};
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}}
QPushButton#Play:hover {{
    background-color: rgba(192, 77, 255, 0.14);
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
    border: 1px solid {PRIMARY};
}}
QCheckBox::indicator:checked {{
    background-color: {PRIMARY};
    border: 1px solid {PRIMARY};
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
    background-color: {PRIMARY};
}}

/* --- Status log --- */
QPlainTextEdit#Log {{
    font-family: {MONO_FONT};
    font-size: 12px;
    color: #E9C7FF;
    background-color: #0A0613;
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
    color: {ACCENT};
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
