"""End-to-end orchestration: download → separate → analyze → export.

Pure, UI-agnostic logic so it can be driven by the Qt worker or headless (CLI /
tests). Reports rich :class:`ProgressEvent`s with a weighted overall percentage
and per-phase ETA, and supports cooperative cancellation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional

from . import analysis as analysis_mod
from . import downloader, exporter, separator
from .config import Secrets, Settings
from .models import (
    AnalysisResult,
    JobCancelled,
    JobRequest,
    ProgressEvent,
    SeparationResult,
    Track,
)

ProgressSink = Callable[[ProgressEvent], None]

# Relative cost of each phase for the overall progress bar. Separation dominates.
PHASE_WEIGHTS = {"download": 0.07, "separation": 0.82, "analysis": 0.05, "export": 0.06}
PHASE_ORDER = ["download", "separation", "analysis", "export"]


def _phase_base(phase: str) -> float:
    """Cumulative weight of all phases before ``phase`` (its overall start %)."""
    base = 0.0
    for p in PHASE_ORDER:
        if p == phase:
            break
        base += PHASE_WEIGHTS[p]
    return base


def _noop(*_args, **_kwargs) -> None:
    pass


@dataclass(slots=True)
class JobResult:
    """Everything produced by one end-to-end run."""

    track: Track
    separation: SeparationResult
    analysis: AnalysisResult
    export: "exporter.ExportResult"


def run_job(
    req: JobRequest,
    settings: Settings,
    secrets: Optional[Secrets] = None,
    on_progress: ProgressSink = _noop,
    on_track: Optional[Callable[[Track], None]] = None,
    on_analysis: Optional[Callable[[AnalysisResult], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> JobResult:
    """Run the whole pipeline for one :class:`JobRequest`.

    Emits :class:`ProgressEvent`s via ``on_progress`` with weighted overall
    progress and ETA. ``on_track`` / ``on_analysis`` fire as soon as those values
    exist. If ``cancel_event`` is set, raises :class:`JobCancelled` at the next
    checkpoint (phase boundary or inference chunk).

    Raises with a readable message on a fatal error. The caller (UI worker) is
    responsible for surfacing it without crashing.
    """
    secrets = secrets or Secrets.from_env()

    def should_cancel() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def check_cancel() -> None:
        if should_cancel():
            raise JobCancelled()

    # Overall progress is kept monotonic so interleaved library log lines
    # (which carry no fraction) never bounce the bar backwards.
    state = {"overall": 0.0}

    def reporter(phase: str) -> Callable[..., None]:
        base = _phase_base(phase)
        weight = PHASE_WEIGHTS[phase]

        def report(message: str, fraction: Optional[float] = None, eta: Optional[float] = None) -> None:
            computed = base + (fraction or 0.0) * weight
            overall = max(state["overall"], computed)
            state["overall"] = overall
            on_progress(ProgressEvent(
                message=message,
                phase=phase,
                phase_fraction=fraction,
                overall_fraction=overall,
                eta_sec=eta,
            ))

        return report

    # 1) Download / load source -------------------------------------------------
    dl = reporter("download")
    dl("Starting…", 0.0)
    track = downloader.resolve_source(req.source, settings.download_path(), dl)
    if on_track:
        on_track(track)
    check_cancel()

    # 2) Separation -------------------------------------------------------------
    sep_report = reporter("separation")
    sep_report("Preparing separation…", 0.0)
    work_dir = settings.download_path() / "_stems" / track.audio_path.stem
    if req.use_ensemble:
        separation = separator.separate_ensemble(
            track.audio_path, settings, work_dir, sep_report, should_cancel=should_cancel
        )
    else:
        separation = separator.separate(
            track.audio_path, req.model_filename, settings, work_dir, sep_report,
            should_cancel=should_cancel,
        )
    check_cancel()

    # 3) Analysis (BPM / key) ---------------------------------------------------
    an = reporter("analysis")
    an("Analyzing tempo & key…", 0.0)
    try:
        analysis = analysis_mod.analyze(track, settings, secrets, an)
    except Exception as exc:  # analysis must never abort a successful separation
        an(f"Analysis failed ({exc}); continuing without BPM/key.")
        analysis = AnalysisResult()
    if on_analysis:
        on_analysis(analysis)
    check_cancel()

    # 4) Export -----------------------------------------------------------------
    ex = reporter("export")
    ex("Exporting…", 0.0)
    export_result = exporter.export(separation, track, analysis, settings, req.selected_stems, ex)

    on_progress(ProgressEvent(message="✓ Done.", phase="export",
                              phase_fraction=1.0, overall_fraction=1.0, eta_sec=0.0))
    return JobResult(track=track, separation=separation, analysis=analysis, export=export_result)
