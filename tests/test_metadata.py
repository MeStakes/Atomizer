"""Tests for embedded Apple Loops 'basc' tempo+key metadata in AIFF exports.

These exercise the best-effort big-endian ``basc`` chunk written into exported
AIFF files (so hosts like MainStage can auto-detect tempo/key), and confirm WAV
exports are unaffected.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import soundfile as sf

from atomizer import exporter
from atomizer.config import Settings
from atomizer.models import (
    AnalysisResult,
    AnalysisSource,
    ModelInfo,
    SeparationResult,
    StemResult,
    Track,
)


def _fake_separation(tmp_path) -> tuple[SeparationResult, Track]:
    stems = []
    for name in ("Vocals", "Drums"):
        p = tmp_path / f"{name}.wav"
        sf.write(str(p), 0.1 * np.random.randn(44100, 2), 44100)
        stems.append(StemResult(name, p))
    sep = SeparationResult(stems=stems, model=ModelInfo("htdemucs_ft.yaml", "HTDemucs"))
    track = Track(tmp_path / "src.wav", title="Title", artist="Artist")
    return sep, track


def _find_basc_payload(raw: bytes) -> bytes:
    """Locate the 'basc' chunk and return its 84-byte payload."""
    idx = raw.find(b"basc")
    assert idx != -1, "basc chunk not found"
    size = struct.unpack(">I", raw[idx + 4:idx + 8])[0]
    assert size == 84
    return raw[idx + 8:idx + 8 + size]


def _parse_basc(payload: bytes) -> dict:
    loopable, num_beats, key_midi, scale, num, denom = struct.unpack(">IIHHHH", payload[:16])
    return {
        "loopable": loopable,
        "num_beats": num_beats,
        "key_midi": key_midi,
        "scale": scale,
        "num": num,
        "denom": denom,
    }


def test_aiff_still_opens_and_has_basc(tmp_path):
    sep, track = _fake_separation(tmp_path)
    a = AnalysisResult(bpm=128.0, key="C major", bpm_source=AnalysisSource.LOCAL,
                       key_source=AnalysisSource.LOCAL)
    s = Settings(output_dir=str(tmp_path / "out"), export_format="AIFF", bit_depth=24)
    res = exporter.export(sep, track, a, s, selected_stems=["Vocals"])

    out = res.files[0].path
    assert out.suffix == ".aif"

    # 1. Still a valid AIFF: opens via soundfile with correct sr/channels/frames.
    data, sr = sf.read(str(out), always_2d=True)
    assert sr == 44100
    assert data.shape[1] == 2
    assert data.shape[0] == 44100

    # 2. Raw bytes carry the basc chunk.
    raw = out.read_bytes()
    assert b"basc" in raw


def test_basc_c_major(tmp_path):
    sep, track = _fake_separation(tmp_path)
    a = AnalysisResult(bpm=120.0, key="C major")
    s = Settings(output_dir=str(tmp_path / "out_cmaj"), export_format="AIFF", bit_depth=24)
    res = exporter.export(sep, track, a, s, selected_stems=["Vocals"])

    raw = res.files[0].path.read_bytes()
    fields = _parse_basc(_find_basc_payload(raw))
    assert fields["loopable"] == 1
    assert fields["scale"] == 2          # major
    assert fields["key_midi"] == 48      # C
    assert fields["num_beats"] > 0
    assert fields["num"] == 4 and fields["denom"] == 4


def test_basc_a_minor(tmp_path):
    sep, track = _fake_separation(tmp_path)
    a = AnalysisResult(bpm=90.0, key="A minor")
    s = Settings(output_dir=str(tmp_path / "out_amin"), export_format="AIFF", bit_depth=24)
    res = exporter.export(sep, track, a, s, selected_stems=["Vocals"])

    raw = res.files[0].path.read_bytes()
    fields = _parse_basc(_find_basc_payload(raw))
    assert fields["scale"] == 1          # minor
    assert fields["key_midi"] == 57      # A
    assert fields["num_beats"] > 0


def test_wav_has_no_basc(tmp_path):
    sep, track = _fake_separation(tmp_path)
    a = AnalysisResult(bpm=120.0, key="C major")
    s = Settings(output_dir=str(tmp_path / "out_wav"), export_format="WAV", bit_depth=24)
    res = exporter.export(sep, track, a, s, selected_stems=["Vocals"])

    raw = res.files[0].path.read_bytes()
    assert b"basc" not in raw


def test_parse_key_variants():
    assert exporter._parse_key("F# major") == (54, 2)
    assert exporter._parse_key("A minor") == (57, 1)
    assert exporter._parse_key("C") == (48, 2)
    assert exporter._parse_key("Am") == (57, 1)
    assert exporter._parse_key("F#m") == (54, 1)
    assert exporter._parse_key("Bb major") == (58, 2)   # Bb -> A#
    assert exporter._parse_key("E minor") == (52, 1)
    assert exporter._parse_key("Db") == (49, 2)          # Db -> C#
    assert exporter._parse_key(None) == (0, 3)
    assert exporter._parse_key("???") == (0, 3)
