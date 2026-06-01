"""End-to-end orchestration: download → separate → analyze → export.

Pure, UI-agnostic logic so it can be driven by the Qt worker or headless (CLI /
tests). Reports progress through a simple ``(message, fraction)`` callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from . import analysis as analysis_mod
from . import downloader, exporter, separator
from .config import Secrets, Settings
from .models import (
    AnalysisResult,
    ExportResult,
    JobRequest,
    SeparationResult,
    Track,
)

ProgressCallback = Callable[[str, Optional[float]], None]


def _noop(_msg: str, _frac: Optional[float]) -> None:
    pass


@dataclass(slots=True)
class JobResult:
    """Everything produced by one end-to-end run."""

    track: Track
    separation: SeparationResult
    analysis: AnalysisResult
    export: ExportResult


def run_job(
    req: JobRequest,
    settings: Settings,
    secrets: Optional[Secrets] = None,
    progress: ProgressCallback = _noop,
    on_track: Optional[Callable[[Track], None]] = None,
    on_analysis: Optional[Callable[[AnalysisResult], None]] = None,
) -> JobResult:
    """Run the whole pipeline for one :class:`JobRequest`.

    Optional ``on_track`` / ``on_analysis`` hooks fire as soon as those values
    are available, so the UI can update the BPM/key panel mid-run.

    Raises with a readable message on a fatal error (download/separation). The
    caller (UI worker) is responsible for surfacing it without crashing.
    """
    secrets = secrets or Secrets.from_env()

    def phase(name: str) -> None:
        progress(f"▶ {name}", None)

    # 1) Download / load source -------------------------------------------------
    phase("Download")
    track = downloader.resolve_source(req.source, settings.download_path(), progress)
    if on_track:
        on_track(track)

    # 2) Separation -------------------------------------------------------------
    phase("Separation")
    work_dir = settings.download_path() / "_stems" / track.audio_path.stem
    if req.use_ensemble:
        separation = separator.separate_ensemble(track.audio_path, settings, work_dir, progress)
    else:
        separation = separator.separate(
            track.audio_path, req.model_filename, settings, work_dir, progress
        )

    # 3) Analysis (BPM / key) ---------------------------------------------------
    phase("Analysis")
    try:
        analysis = analysis_mod.analyze(track, settings, secrets, progress)
    except Exception as exc:  # analysis must never abort a successful separation
        progress(f"Analysis failed ({exc}); continuing without BPM/key.", None)
        analysis = AnalysisResult()
    if on_analysis:
        on_analysis(analysis)

    # 4) Export -----------------------------------------------------------------
    phase("Export")
    export_result = exporter.export(
        separation, track, analysis, settings, req.selected_stems, progress
    )

    progress("✓ Done.", 1.0)
    return JobResult(track=track, separation=separation, analysis=analysis, export=export_result)
