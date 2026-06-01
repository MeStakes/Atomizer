"""Offline unit tests for Atomizer.

These mock/avoid the heavy MLX separator and the network. They exercise the
pure logic: metadata parsing, key detection, stem mapping, settings, and a real
export of synthetic audio.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from atomizer import analysis, downloader, exporter, separator
from atomizer.config import Secrets, Settings
from atomizer.models import (
    AnalysisResult,
    AnalysisSource,
    ExportFormat,
    ModelInfo,
    SeparationResult,
    StemResult,
    Track,
    to_info_dict,
)


# --------------------------------------------------------------------- models
def test_track_display_name():
    assert Track(Path("x.wav"), title="Song", artist="Band").display_name == "Band - Song"
    assert Track(Path("x.wav"), title="Song").display_name == "Song"
    assert Track(Path("/a/b/My File.wav")).display_name == "My File"


def test_export_format_extension():
    assert ExportFormat.AIFF.extension == ".aif"
    assert ExportFormat.WAV.extension == ".wav"


def test_to_info_dict():
    t = Track(Path("x.wav"), title="T", artist="A", source_url="http://u")
    a = AnalysisResult(bpm=120.0, key="A minor", bpm_source=AnalysisSource.LOCAL,
                       key_source=AnalysisSource.ONLINE)
    sep = SeparationResult(stems=[StemResult("Vocals", Path("v.wav"))],
                           model=ModelInfo("m.ckpt", "M"))
    d = to_info_dict(t, a, sep, created_iso="2026-06-01T00:00:00")
    assert d["bpm"] == 120.0
    assert d["key"] == "A minor"
    assert d["bpm_source"] == "local"
    assert d["key_source"] == "online"
    assert d["stems"] == ["Vocals"]


# ----------------------------------------------------------------- downloader
def test_is_url():
    assert downloader.is_url("https://youtube.com/x")
    assert downloader.is_url("HTTP://x")
    assert not downloader.is_url("/path/to/file.wav")
    assert not downloader.is_url("song.mp3")


def test_split_artist_title():
    a, t = downloader._split_artist_title({"title": "Daft Punk - Get Lucky (Official Video)"})
    assert a == "Daft Punk"
    assert t == "Get Lucky"
    a, t = downloader._split_artist_title({"artist": "Band", "track": "Tune", "title": "x"})
    assert (a, t) == ("Band", "Tune")


def test_track_from_local_file(tmp_path):
    p = tmp_path / "Artist - Title.wav"
    sf.write(str(p), np.zeros((1000, 2)), 44100)
    tr = downloader.track_from_local_file(p)
    assert tr.artist == "Artist" and tr.title == "Title"
    with pytest.raises(FileNotFoundError):
        downloader.track_from_local_file(tmp_path / "missing.wav")
    bad = tmp_path / "x.txt"
    bad.write_text("nope")
    with pytest.raises(ValueError):
        downloader.track_from_local_file(bad)


# ------------------------------------------------------------------- analysis
def test_krumhansl_detects_c_major():
    # A chroma vector strongly weighted on C, E, G (C major triad).
    chroma = np.array([1.0, 0.1, 0.2, 0.1, 0.8, 0.2, 0.1, 0.9, 0.1, 0.2, 0.1, 0.2])
    key, conf = analysis._estimate_key_krumhansl(chroma)
    assert key.startswith("C")
    assert 0.0 <= conf <= 1.0


def test_krumhansl_detects_a_minor():
    # A minor triad: A, C, E.
    chroma = np.zeros(12)
    chroma[9] = 1.0  # A
    chroma[0] = 0.8  # C
    chroma[4] = 0.8  # E
    key, _ = analysis._estimate_key_krumhansl(chroma)
    assert "minor" in key


def test_analyze_local_synthetic(tmp_path):
    # 3s of a 440 Hz tone — exercises the real librosa path (key/BPM may vary).
    sr = 22050
    t = np.linspace(0, 3, sr * 3, endpoint=False)
    y = 0.3 * np.sin(2 * np.pi * 440 * t)
    p = tmp_path / "tone.wav"
    sf.write(str(p), y, sr)
    res = analysis.analyze_local(p)
    assert res.bpm_source == AnalysisSource.LOCAL
    assert res.key is not None
    assert res.bpm is not None


def test_analyze_offline_falls_back(tmp_path, monkeypatch):
    # No API keys → must use local analysis without touching the network.
    monkeypatch.delenv("GETSONGBPM_API_KEY", raising=False)
    monkeypatch.delenv("TUNEBAT_API_KEY", raising=False)
    sr = 22050
    y = 0.2 * np.sin(2 * np.pi * 330 * np.linspace(0, 2, sr * 2, endpoint=False))
    p = tmp_path / "t.wav"
    sf.write(str(p), y, sr)
    track = Track(p, title="x")
    res = analysis.analyze(track, Settings(), Secrets())
    assert res.bpm_source == AnalysisSource.LOCAL


# ------------------------------------------------------------------ separator
def test_clean_and_display_stem():
    assert separator._clean_stem("vocals* (10.8)") == "vocals"
    assert separator._clean_stem("Instrumental") == "instrumental"
    assert separator._display_stem("vocals") == "Vocals"


def test_map_outputs_to_stems():
    model = ModelInfo("m", "M", stems=["Vocals", "Instrumental"])
    files = ["/o/song_(Instrumental)_m.wav", "/o/song_(Vocals)_m.wav"]
    res = separator._map_outputs_to_stems(files, model)
    by = {r.name: r.path.name for r in res}
    assert "Vocals" in by and "Instrumental" in by
    assert "Vocals" in by["Vocals"]


# -------------------------------------------------------------------- config
def test_settings_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    monkeypatch.setattr("atomizer.config._settings_path", lambda: target)
    s = Settings(export_format="WAV", bit_depth=16, default_model="foo.ckpt")
    s.save()
    loaded = Settings.load()
    assert loaded.export_format == "WAV"
    assert loaded.bit_depth == 16
    assert loaded.default_model == "foo.ckpt"


def test_secrets_from_env(monkeypatch):
    monkeypatch.setenv("GETSONGBPM_API_KEY", "abc")
    monkeypatch.delenv("TUNEBAT_API_KEY", raising=False)
    sec = Secrets.from_env()
    assert sec.getsongbpm_api_key == "abc"
    assert sec.has_online_provider()
    assert not Secrets().has_online_provider()


# -------------------------------------------------------------------- export
def _fake_separation(tmp_path) -> tuple[SeparationResult, Track]:
    stems = []
    for name in ("Vocals", "Drums"):
        p = tmp_path / f"{name}.wav"
        sf.write(str(p), 0.1 * np.random.randn(44100, 2), 44100)
        stems.append(StemResult(name, p))
    sep = SeparationResult(stems=stems, model=ModelInfo("htdemucs_ft.yaml", "HTDemucs"))
    track = Track(tmp_path / "src.wav", title="Title", artist="Artist")
    return sep, track


def test_export_aiff(tmp_path):
    sep, track = _fake_separation(tmp_path)
    a = AnalysisResult(bpm=128.0, key="A minor", bpm_source=AnalysisSource.LOCAL,
                       key_source=AnalysisSource.LOCAL)
    s = Settings(output_dir=str(tmp_path / "out"), export_format="AIFF", bit_depth=24)
    res = exporter.export(sep, track, a, s, selected_stems=["Vocals"])
    assert res.folder.exists()
    assert "Artist - Title (128 BPM - A minor)" in res.folder.name
    assert len(res.files) == 1  # only the selected stem
    out = res.files[0].path
    assert out.suffix == ".aif"
    data, sr = sf.read(str(out))
    assert sr == 44100 and data.shape[1] == 2
    assert res.info_path.exists()


def test_export_wav_acid_chunk_readable(tmp_path):
    sep, track = _fake_separation(tmp_path)
    a = AnalysisResult(bpm=120.0, key="C major")
    s = Settings(output_dir=str(tmp_path / "out2"), export_format="WAV", bit_depth=24)
    res = exporter.export(sep, track, a, s, selected_stems=["Vocals", "Drums"])
    assert len(res.files) == 2
    for f in res.files:
        # acid chunk appended must not corrupt the file.
        data, sr = sf.read(str(f.path))
        assert sr == 44100
        raw = f.path.read_bytes()
        assert b"acid" in raw  # tempo chunk present


def test_folder_name_without_metadata(tmp_path):
    track = Track(tmp_path / "x.wav", title="Solo")
    a = AnalysisResult()  # no bpm/key
    name = exporter.folder_name(track, a)
    assert name == "Solo"
