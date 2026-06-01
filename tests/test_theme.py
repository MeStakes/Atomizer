"""Sanity checks for the synthwave neon palette."""

from __future__ import annotations

from atomizer.ui import theme


def test_synthwave_accents_defined():
    assert theme.PRIMARY == "#C04DFF"
    assert theme.ACCENT == "#FF4DD8"
    assert theme.DEEP == "#6A2BFF"


def test_qss_uses_violet_primary():
    assert theme.PRIMARY in theme.QSS


def test_qss_has_no_old_cyan():
    # Old cyan/teal accents must be fully gone.
    for stale in ("#00E5FF", "#00FFC6", "#B14EFF"):
        assert stale not in theme.QSS
    # Semantic constants must no longer exist.
    assert not hasattr(theme, "CYAN")
    assert not hasattr(theme, "AQUA")
    assert not hasattr(theme, "VIOLET")
