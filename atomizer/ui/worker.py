"""Background worker: runs the pipeline off the UI thread and emits signals.

Qt delivers cross-thread signals via queued connections, so the pipeline's
progress/event callbacks (which fire on this thread) safely update the UI.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..config import Secrets, Settings
from ..models import AnalysisResult, JobRequest, Track
from ..pipeline import JobResult, run_job


class JobWorker(QThread):
    """Runs one :class:`JobRequest` end-to-end."""

    progress = Signal(str, float)   # (message, fraction or -1 for indeterminate)
    trackReady = Signal(object)     # Track
    analysisReady = Signal(object)  # AnalysisResult
    succeeded = Signal(object)      # JobResult
    failed = Signal(str)

    def __init__(self, request: JobRequest, settings: Settings,
                 secrets: Optional[Secrets] = None, parent=None) -> None:
        super().__init__(parent)
        self._req = request
        self._settings = settings
        self._secrets = secrets

    def _progress(self, message: str, frac: Optional[float]) -> None:
        self.progress.emit(message, -1.0 if frac is None else float(frac))

    def run(self) -> None:  # noqa: D401
        try:
            result: JobResult = run_job(
                self._req,
                self._settings,
                self._secrets,
                progress=self._progress,
                on_track=lambda t: self.trackReady.emit(t),
                on_analysis=lambda a: self.analysisReady.emit(a),
            )
            self.succeeded.emit(result)
        except Exception as exc:  # surface, never crash the UI
            self.failed.emit(str(exc))
