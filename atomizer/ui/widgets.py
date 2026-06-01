"""Custom neon widgets for Atomizer's UI."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme

_AUDIO_FILTER = "Audio (*.wav *.aif *.aiff *.flac *.mp3 *.m4a *.opus *.ogg);;All files (*)"


class LogoLabel(QWidget):
    """Paints the 'ATOMIZER' wordmark with a cyan→violet gradient and glow."""

    def __init__(self, text: str = "ATOMIZER", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text = text
        self.setMinimumHeight(56)
        font = QFont()
        font.setFamilies(["Orbitron", "Space Grotesk", "SF Pro Display", "Helvetica Neue"])
        font.setPointSize(34)
        font.setWeight(QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
        self._font = font
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(28)
        glow.setColor(QColor(theme.CYAN))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self._font)
        rect = self.rect()
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        grad.setColorAt(0.0, QColor(theme.CYAN))
        grad.setColorAt(0.55, QColor(theme.AQUA))
        grad.setColorAt(1.0, QColor(theme.VIOLET))
        p.setPen(QPen(grad, 0))
        p.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()


class DropZone(QFrame):
    """URL field + browse button inside a drag-and-drop target.

    Emits :attr:`sourceChanged` whenever the source (URL or local file) changes.
    """

    sourceChanged = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        hint = QLabel("Paste a URL (YouTube…) or drop / choose a local audio file")
        hint.setObjectName("Hint")
        lay.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://…  or  /path/to/song.wav")
        self.url_edit.textChanged.connect(self.sourceChanged.emit)
        browse = QPushButton("Browse…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse)
        row.addWidget(self.url_edit, 1)
        row.addWidget(browse)
        lay.addLayout(row)

    def current_source(self) -> str:
        return self.url_edit.text().strip()

    def set_source(self, value: str) -> None:
        self.url_edit.setText(value)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose audio file", str(_home()), _AUDIO_FILTER)
        if path:
            self.set_source(path)

    # --- drag & drop ---
    def _set_drag(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            self._set_drag(True)
            e.acceptProposedAction()

    def dragLeaveEvent(self, _e) -> None:  # noqa: N802
        self._set_drag(False)

    def dropEvent(self, e) -> None:  # noqa: N802
        self._set_drag(False)
        md = e.mimeData()
        if md.hasUrls():
            url = md.urls()[0]
            self.set_source(url.toLocalFile() if url.isLocalFile() else url.toString())
        elif md.hasText():
            self.set_source(md.text().strip())
        e.acceptProposedAction()


class NeonProgressBar(QProgressBar):
    """Progress bar with an animated neon glow; supports a pulsing busy mode."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTextVisible(True)
        self.setRange(0, 100)
        self.setValue(0)

        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setColor(QColor(theme.CYAN))
        self._glow.setOffset(0, 0)
        self._glow.setBlurRadius(8)
        self.setGraphicsEffect(self._glow)

        self._pulse = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._pulse.setStartValue(8)
        self._pulse.setEndValue(30)
        self._pulse.setDuration(900)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)

    def start_pulse(self) -> None:
        self._pulse.start()

    def stop_pulse(self) -> None:
        self._pulse.stop()
        self._glow.setBlurRadius(8)

    def set_busy(self, busy: bool) -> None:
        """Indeterminate marching mode with pulsing glow."""
        if busy:
            self.setRange(0, 0)
            self.start_pulse()
        else:
            self.setRange(0, 100)

    def set_progress(self, frac: float) -> None:
        """Determinate progress in [0, 1]."""
        self.setRange(0, 100)
        self.setValue(int(max(0.0, min(1.0, frac)) * 100))


class MetricChip(QWidget):
    """A BPM or Key readout with a big value, label, and source/confidence badge."""

    def __init__(self, label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)

        self._caption = QLabel(label)
        self._caption.setObjectName("MetricLabel")
        self._value = QLabel("—")
        self._value.setObjectName("MetricValue")
        self._badge = QLabel("")
        self._badge.setObjectName("SourceBadge")

        lay.addWidget(self._caption)
        lay.addWidget(self._value)
        lay.addWidget(self._badge)

    def set_value(self, value: str, source: str = "", confidence: Optional[float] = None) -> None:
        self._value.setText(value or "—")
        badge = ""
        if source and source != "unknown":
            badge = f"● {source}"
            if confidence is not None:
                badge += f"  ·  {confidence * 100:.0f}% conf"
        self._badge.setText(badge)
        color = theme.AQUA if source == "online" else (theme.VIOLET if source == "local" else theme.TEXT_MUTED)
        self._badge.setStyleSheet(f"color: {color};")


def _home():
    return os.path.expanduser("~")
