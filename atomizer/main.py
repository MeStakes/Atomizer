"""Atomizer entrypoint: build the QApplication, show a splash, open the window.

Run with:  python -m atomizer.main
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from . import __tagline__, __version__
from .ui import theme
from .ui.main_window import MainWindow


def _make_splash_pixmap() -> QPixmap:
    """Render the ATOMIZER splash to a pixmap (near-black with neon wordmark)."""
    w, h = 620, 320
    pm = QPixmap(w, h)
    pm.fill(QColor(theme.BG_DEEP))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # subtle border
    p.setPen(QPen(QColor(theme.BORDER), 1))
    p.drawRoundedRect(8, 8, w - 16, h - 16, 18, 18)

    # wordmark with gradient
    font = QFont()
    font.setFamilies(["Orbitron", "Space Grotesk", "SF Pro Display", "Helvetica Neue"])
    font.setPointSize(46)
    font.setWeight(QFont.Weight.Black)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8)
    p.setFont(font)
    grad = QLinearGradient(0, 0, w, 0)
    grad.setColorAt(0.0, QColor(theme.PRIMARY))
    grad.setColorAt(0.55, QColor(theme.ACCENT))
    grad.setColorAt(1.0, QColor(theme.DEEP))
    p.setPen(QPen(grad, 0))
    p.drawText(pm.rect().adjusted(0, -20, 0, -20), Qt.AlignmentFlag.AlignCenter, "ATOMIZER")

    # tagline
    sub = QFont()
    sub.setFamilies(["Space Grotesk", "Inter", "Helvetica Neue"])
    sub.setPointSize(12)
    p.setFont(sub)
    p.setPen(QPen(QColor(theme.TEXT_MUTED)))
    p.drawText(
        pm.rect().adjusted(0, 90, 0, 90),
        Qt.AlignmentFlag.AlignCenter,
        f"{__tagline__}   ·   v{__version__}",
    )
    p.end()
    return pm


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Atomizer")
    app.setApplicationDisplayName("Atomizer")

    base = QFont()
    base.setFamilies(["Space Grotesk", "Inter", "SF Pro Text", "Helvetica Neue"])
    base.setPointSize(13)
    app.setFont(base)
    app.setStyleSheet(theme.QSS)

    splash = QSplashScreen(_make_splash_pixmap())
    splash.show()
    app.processEvents()

    window = MainWindow()

    def _go() -> None:
        window.show()
        splash.finish(window)

    QTimer.singleShot(1200, _go)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
