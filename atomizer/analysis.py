"""Detect BPM and musical key.

Strategy: try an online provider first (faster and often more accurate, keyed by
title + artist), then fall back to a fully local computation with librosa. The
result always records its source (online/local) and a confidence value so the UI
can be honest about provenance.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .config import Secrets, Settings
from .models import AnalysisResult, AnalysisSource, Track

ProgressCallback = Callable[..., None]


def _noop(*_args, **_kwargs) -> None:
    pass


# Pitch classes, index 0 == C.
_PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)


# ----------------------------------------------------------------------------
# Local analysis (librosa)
# ----------------------------------------------------------------------------
def _estimate_key_krumhansl(chroma_mean: np.ndarray) -> tuple[str, float]:
    """Return (key_name, confidence 0..1) from a 12-dim mean chroma vector.

    Correlates the chroma against all 24 major/minor key profiles (Krumhansl-
    Schmuckler) and picks the best. Confidence is derived from the margin between
    the best and second-best correlation.
    """
    chroma_mean = chroma_mean - chroma_mean.mean()
    scores: list[tuple[float, str]] = []
    for tonic in range(12):
        maj = np.roll(_MAJOR_PROFILE - _MAJOR_PROFILE.mean(), tonic)
        minp = np.roll(_MINOR_PROFILE - _MINOR_PROFILE.mean(), tonic)
        # Pearson correlation == normalized dot product of zero-mean vectors.
        for prof, mode in ((maj, "major"), (minp, "minor")):
            denom = np.linalg.norm(chroma_mean) * np.linalg.norm(prof)
            corr = float(np.dot(chroma_mean, prof) / denom) if denom else 0.0
            scores.append((corr, f"{_PITCHES[tonic]} {mode}"))

    scores.sort(reverse=True)
    best_corr, best_key = scores[0]
    second_corr = scores[1][0]
    # Confidence: blend absolute correlation with the margin over runner-up.
    margin = max(0.0, best_corr - second_corr)
    confidence = float(np.clip(0.5 * max(0.0, best_corr) + 5.0 * margin, 0.0, 1.0))
    return best_key, confidence


def analyze_local(audio_path, progress: ProgressCallback = _noop) -> AnalysisResult:
    """Compute BPM and key locally from the audio waveform with librosa."""
    import librosa  # lazy: heavy import

    progress("Analyzing audio (local: BPM + key)…", None)
    # Mono, native sample rate is fine for tempo/chroma.
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)

    # --- BPM ---
    tempo, _beats = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    # --- Key (harmonic component improves chroma) ---
    y_harm = librosa.effects.harmonic(y)
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    key, key_conf = _estimate_key_krumhansl(chroma_mean)

    return AnalysisResult(
        bpm=round(bpm, 2),
        key=key,
        bpm_source=AnalysisSource.LOCAL,
        key_source=AnalysisSource.LOCAL,
        bpm_confidence=0.7,  # librosa beat_track is reliable but gives no score
        key_confidence=round(key_conf, 2),
    )


# ----------------------------------------------------------------------------
# Online analysis
# ----------------------------------------------------------------------------
def _lookup_getsongbpm(track: Track, api_key: str, timeout: float = 8.0) -> Optional[AnalysisResult]:
    """Look up BPM/key on GetSongBPM by 'song:title artist'. None on any failure."""
    if not (track.title):
        return None
    import requests

    query = track.title if not track.artist else f"{track.title} {track.artist}"
    try:
        resp = requests.get(
            "https://api.getsongbpm.com/search/",
            params={"api_key": api_key, "type": "song", "lookup": query},
            timeout=timeout,
            headers={"User-Agent": "Atomizer/0.1"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    results = data.get("search")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    tempo = first.get("tempo")
    key_of = first.get("key_of")
    bpm = float(tempo) if tempo not in (None, "", "0") else None
    if bpm is None and not key_of:
        return None
    return AnalysisResult(
        bpm=bpm,
        key=key_of or None,
        bpm_source=AnalysisSource.ONLINE if bpm else AnalysisSource.UNKNOWN,
        key_source=AnalysisSource.ONLINE if key_of else AnalysisSource.UNKNOWN,
        bpm_confidence=0.9 if bpm else None,
        key_confidence=0.9 if key_of else None,
    )


def _lookup_tunebat(track: Track, secrets: Secrets, timeout: float = 8.0) -> Optional[AnalysisResult]:
    """Look up BPM/key via a Tunebat (RapidAPI) proxy. None on any failure."""
    if not track.title or not secrets.tunebat_api_key or not secrets.tunebat_api_host:
        return None
    import requests

    query = track.title if not track.artist else f"{track.artist} {track.title}"
    try:
        resp = requests.get(
            f"https://{secrets.tunebat_api_host}/api/tunebat/search",
            params={"term": query},
            headers={
                "X-RapidAPI-Key": secrets.tunebat_api_key,
                "X-RapidAPI-Host": secrets.tunebat_api_host,
                "User-Agent": "Atomizer/0.1",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    items = (data.get("data") or {}).get("items") if isinstance(data.get("data"), dict) else data.get("data")
    if not items:
        return None
    first = items[0]
    bpm = first.get("bpm")
    key = first.get("key") or first.get("camelot")
    if bpm is None and key is None:
        return None
    return AnalysisResult(
        bpm=float(bpm) if bpm else None,
        key=str(key) if key else None,
        bpm_source=AnalysisSource.ONLINE if bpm else AnalysisSource.UNKNOWN,
        key_source=AnalysisSource.ONLINE if key else AnalysisSource.UNKNOWN,
        bpm_confidence=0.85 if bpm else None,
        key_confidence=0.85 if key else None,
    )


def analyze_online(track: Track, settings: Settings, secrets: Secrets) -> Optional[AnalysisResult]:
    """Try the configured online provider. None if unavailable or no match."""
    if not secrets.has_online_provider():
        return None
    provider = (settings.bpm_key_provider or "getsongbpm").lower()
    order = ["getsongbpm", "tunebat"] if provider == "getsongbpm" else ["tunebat", "getsongbpm"]
    for name in order:
        if name == "getsongbpm" and secrets.getsongbpm_api_key:
            res = _lookup_getsongbpm(track, secrets.getsongbpm_api_key)
        elif name == "tunebat":
            res = _lookup_tunebat(track, secrets)
        else:
            res = None
        if res and (res.bpm or res.key):
            return res
    return None


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def analyze(
    track: Track,
    settings: Settings,
    secrets: Optional[Secrets] = None,
    progress: ProgressCallback = _noop,
) -> AnalysisResult:
    """Detect BPM/key, online-first when configured, else local librosa.

    Always returns a result; missing online data is backfilled locally so the
    user still gets BPM and key even with no API key or no network.
    """
    secrets = secrets or Secrets.from_env()

    online: Optional[AnalysisResult] = None
    if settings.prefer_online_analysis and secrets.has_online_provider():
        progress("Looking up BPM/key online…", None)
        try:
            online = analyze_online(track, settings, secrets)
        except Exception:
            online = None

    # If online gave us both fields, we're done.
    if online and online.bpm and online.key:
        return online

    # Otherwise compute locally and merge: prefer any online value we did get.
    local = analyze_local(track.audio_path, progress)
    if not online:
        return local

    return AnalysisResult(
        bpm=online.bpm or local.bpm,
        key=online.key or local.key,
        bpm_source=online.bpm_source if online.bpm else local.bpm_source,
        key_source=online.key_source if online.key else local.key_source,
        bpm_confidence=online.bpm_confidence if online.bpm else local.bpm_confidence,
        key_confidence=online.key_confidence if online.key else local.key_confidence,
    )
