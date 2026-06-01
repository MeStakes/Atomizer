"""Background worker: runs one job off the UI thread and emits Qt signals.

Qt delivers cross-thread signals via queued connections, so the pipeline's
progress/event callbacks (which fire on this thread) safely update the UI.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..config import Secrets, Settings
from ..models import JobCancelled, JobRequest
from ..pipeline import JobResult, run_job


class JobWorker(QThread):
    """Runs one :class:`JobRequest` end-to-end, with cooperative cancel."""

    progress = Signal(object)       # ProgressEvent
    trackReady = Signal(object)     # Track
    analysisReady = Signal(object)  # AnalysisResult
    succeeded = Signal(object)      # JobResult
    failed = Signal(str)
    canceled = Signal()

    def __init__(self, request: JobRequest, settings: Settings,
                 secrets: Optional[Secrets] = None, parent=None) -> None:
        super().__init__(parent)
        self._req = request
        self._settings = settings
        self._secrets = secrets
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; takes effect at the next pipeline checkpoint."""
        self._cancel.set()

    def run(self) -> None:  # noqa: D401
        try:
            result: JobResult = run_job(
                self._req,
                self._settings,
                self._secrets,
                on_progress=lambda ev: self.progress.emit(ev),
                on_track=lambda t: self.trackReady.emit(t),
                on_analysis=lambda a: self.analysisReady.emit(a),
                cancel_event=self._cancel,
            )
            self.succeeded.emit(result)
        except JobCancelled:
            self.canceled.emit()
        except Exception as exc:  # surface, never crash the UI
            self.failed.emit(str(exc))
