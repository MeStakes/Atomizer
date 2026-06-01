"""Thin wrapper around ``mlx-audio-separator``.

Isolates every call into the library behind a small, stable interface:
list models, pre-download a model (first-run), and separate an audio file into
its stems. Also implements an optional manual ensemble (waveform averaging) for
models that share the same stem taxonomy, with a graceful fallback to the single
best model when ensembling is not applicable.

The heavy library is imported lazily so the rest of the app (and tests) stay
cheap to import.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional

from .config import DEFAULT_MODEL, Settings
from .models import ModelInfo, SeparationResult, StemResult

ProgressCallback = Callable[[str, Optional[float]], None]


def _noop(_msg: str, _frac: Optional[float]) -> None:
    pass


# Curated, quality-first recommendations. Order = display order in the UI.
_RECOMMENDED: dict[str, dict] = {
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": {
        "display": "BS-Roformer (Vocals) — Highest quality",
        "quality": "Highest",
        "description": "SDX23 winner. Best vocal/instrumental split (~12.9 dB SDR). Slowest.",
    },
    "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt": {
        "display": "MelBand-Roformer (Vocals) — Very high",
        "quality": "Very high",
        "description": "Excellent vocal/instrumental split. Great alternative to BS-Roformer.",
    },
    "htdemucs_ft.yaml": {
        "display": "HTDemucs FT — 4 stems (vocals/drums/bass/other)",
        "quality": "High (4-stem)",
        "description": "Fine-tuned Demucs. Full band split into 4 stems.",
    },
    "htdemucs_6s.yaml": {
        "display": "HTDemucs 6s — 6 stems (+guitar/piano)",
        "quality": "High (6-stem)",
        "description": "6-stem split adding guitar and piano. Use when you need those.",
    },
}

# Compatible pairs for the optional manual ensemble (same stem taxonomy).
_ENSEMBLE_VOCAL_MODELS = [
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
]


def _clean_stem(raw: str) -> str:
    """'vocals* (10.8)' -> 'vocals' (lowercased, annotations stripped)."""
    s = re.sub(r"\(.*?\)", "", raw)  # drop "(10.8)"
    s = s.replace("*", "").strip()
    return s.lower()


def _display_stem(name: str) -> str:
    """'vocals' -> 'Vocals'."""
    return name.strip().title()


def _make_separator(settings: Settings, output_dir: Path, log_handler: logging.Handler):
    """Construct the library Separator with our paths/format. Lazy import."""
    from mlx_audio_separator import Separator

    # Forward the library's INFO logs to the UI progress callback.
    lib_logger = logging.getLogger("mlx_audio_separator")
    lib_logger.setLevel(logging.INFO)
    for h in list(lib_logger.handlers):
        if getattr(h, "_atomizer", False):
            lib_logger.removeHandler(h)
    lib_logger.addHandler(log_handler)

    return Separator(
        log_level=logging.INFO,
        model_file_dir=str(settings.model_cache_path()),
        output_dir=str(output_dir),
        output_format="WAV",  # lossless intermediate; exporter makes the final file
        sample_rate=settings.sample_rate,
    )


class _ProgressLogHandler(logging.Handler):
    """Logging handler that pipes library log records to a progress callback."""

    def __init__(self, progress: ProgressCallback) -> None:
        super().__init__(level=logging.INFO)
        self._progress = progress
        self._atomizer = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if msg:
                self._progress(msg, None)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Model listing
# ----------------------------------------------------------------------------
def list_models(settings: Settings, recommended_only: bool = False) -> list[ModelInfo]:
    """Return available models as :class:`ModelInfo`, recommended ones first.

    Pulls the catalogue from the library at runtime so the UI never hardcodes
    filenames. On any failure, returns the curated recommended set so the UI
    still works offline-ish (those models download on demand).
    """
    catalogue: dict[str, dict] = {}
    try:
        from mlx_audio_separator import Separator

        sep = Separator(info_only=True, model_file_dir=str(settings.model_cache_path()))
        catalogue = sep.get_simplified_model_list() or {}
    except Exception:
        catalogue = {}

    def build(filename: str, meta: dict) -> ModelInfo:
        rec = _RECOMMENDED.get(filename)
        stems_raw = meta.get("Stems", []) if isinstance(meta, dict) else []
        stems = [_display_stem(_clean_stem(s)) for s in stems_raw if _clean_stem(s) not in ("", "unknown")]
        return ModelInfo(
            filename=filename,
            display_name=rec["display"] if rec else (meta.get("Name") or filename),
            architecture=meta.get("Type", "") if isinstance(meta, dict) else "",
            description=rec["description"] if rec else "",
            quality=rec["quality"] if rec else "",
            recommended=rec is not None,
            stems=stems,
        )

    models: list[ModelInfo] = []

    # Recommended first, in our curated order.
    for fname in _RECOMMENDED:
        meta = catalogue.get(fname, {})
        models.append(build(fname, meta))

    if not recommended_only:
        for fname, meta in catalogue.items():
            if fname in _RECOMMENDED:
                continue
            models.append(build(fname, meta))

    return models


def default_model_info(settings: Settings) -> ModelInfo:
    """The model selected at launch: highest-quality vocal model."""
    for m in list_models(settings, recommended_only=True):
        if m.filename == DEFAULT_MODEL:
            return m
    # Fallback if catalogue lookup failed.
    return ModelInfo(filename=DEFAULT_MODEL, display_name="BS-Roformer (Vocals)", recommended=True,
                     stems=["Vocals", "Instrumental"])


# ----------------------------------------------------------------------------
# Model download (first run)
# ----------------------------------------------------------------------------
def ensure_model(settings: Settings, model_filename: str, progress: ProgressCallback = _noop) -> None:
    """Download model checkpoints if not already present (first-run)."""
    from mlx_audio_separator import Separator

    progress(f"Preparing model {model_filename} (first run may download 100s MB–GB)…", None)
    sep = Separator(info_only=True, model_file_dir=str(settings.model_cache_path()))
    try:
        sep.download_model_files(model_filename)
    except Exception as exc:
        raise RuntimeError(f"Failed to download model '{model_filename}': {exc}") from exc


# ----------------------------------------------------------------------------
# Separation
# ----------------------------------------------------------------------------
def _map_outputs_to_stems(output_files: list[str], model: ModelInfo) -> list[StemResult]:
    """Match the library's output file paths to stem names.

    Matches by looking for the stem token in each filename; falls back to
    positional assignment if detection is ambiguous.
    """
    paths = [Path(p) for p in output_files]
    results: list[StemResult] = []
    used: set[Path] = set()

    expected = model.stems or []
    for stem in expected:
        token = stem.lower()
        match = next(
            (p for p in paths if p not in used and token in p.name.lower()), None
        )
        if match:
            used.add(match)
            results.append(StemResult(name=stem, path=match))

    # Any unmatched output files: name them from the filename or generically.
    leftovers = [p for p in paths if p not in used]
    for i, p in enumerate(leftovers):
        m = re.search(r"\(([^)]+)\)", p.stem)  # e.g. "..._(Instrumental)_..."
        name = _display_stem(m.group(1)) if m else f"Stem {len(results) + 1}"
        results.append(StemResult(name=name, path=p))

    return results


def separate(
    audio_path,
    model_filename: str,
    settings: Settings,
    output_dir,
    progress: ProgressCallback = _noop,
    model_info: Optional[ModelInfo] = None,
) -> SeparationResult:
    """Separate ``audio_path`` with one model into all of its stems."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if model_info is None:
        model_info = next(
            (m for m in list_models(settings) if m.filename == model_filename),
            ModelInfo(filename=model_filename, display_name=model_filename),
        )

    ensure_model(settings, model_filename, progress)

    handler = _ProgressLogHandler(progress)
    progress(f"Separating with {model_info.display_name}… (this can take several minutes)", None)
    sep = _make_separator(settings, output_dir, handler)
    sep.load_model(model_filename=model_filename)
    output_files = sep.separate(str(audio_path))

    stems = _map_outputs_to_stems(list(output_files), model_info)
    progress(f"Separation complete: {len(stems)} stem(s).", 1.0)
    return SeparationResult(stems=stems, model=model_info, ensemble_used=False)


def separate_ensemble(
    audio_path,
    settings: Settings,
    output_dir,
    progress: ProgressCallback = _noop,
) -> SeparationResult:
    """Optional manual ensemble across vocal models with identical stems.

    Runs each compatible model, then averages aligned stem waveforms for maximum
    quality. Falls back gracefully to the single best model when fewer than two
    compatible models succeed.
    """
    import numpy as np
    import soundfile as sf

    output_dir = Path(output_dir)
    runs: list[SeparationResult] = []
    for fname in _ENSEMBLE_VOCAL_MODELS:
        try:
            sub = output_dir / f"_ens_{Path(fname).stem[:24]}"
            runs.append(separate(audio_path, fname, settings, sub, progress))
        except Exception as exc:
            progress(f"Ensemble member '{fname}' failed: {exc}", None)

    if len(runs) < 2:
        # Graceful fallback to the single best model.
        progress("Ensemble unavailable — falling back to the single best model.", None)
        best = runs[0] if runs else separate(audio_path, DEFAULT_MODEL, settings, output_dir, progress)
        best.note = "ensemble not available; used single best model"
        return best

    # Average per stem name across runs (truncate to the shortest length).
    progress("Averaging ensemble stems…", None)
    base = runs[0]
    averaged: list[StemResult] = []
    for stem in base.stems:
        arrays, sr = [], None
        for run in runs:
            s = run.stem(stem.name)
            if not s:
                continue
            data, this_sr = sf.read(str(s.path), always_2d=True)
            sr = this_sr if sr is None else sr
            arrays.append(data)
        if not arrays or sr is None:
            continue
        n = min(a.shape[0] for a in arrays)
        ch = min(a.shape[1] for a in arrays)
        stacked = np.stack([a[:n, :ch] for a in arrays], axis=0)
        mixed = stacked.mean(axis=0)
        out_path = output_dir / f"ensemble_{stem.name}.wav"
        sf.write(str(out_path), mixed, sr)
        averaged.append(StemResult(name=stem.name, path=out_path))

    model = ModelInfo(
        filename="ensemble",
        display_name="Ensemble (BS-Roformer + MelBand-Roformer)",
        architecture="Ensemble",
        recommended=True,
        stems=[s.name for s in averaged],
    )
    progress(f"Ensemble complete: {len(averaged)} stem(s).", 1.0)
    return SeparationResult(stems=averaged, model=model, ensemble_used=True,
                            note="manual waveform-average ensemble")
