"""Sequential job queue controller.

Holds a list of :class:`QueuedJob`s and runs them one at a time. Adding a job
auto-starts it when the queue is idle. Forwards the active job's progress/track/
analysis signals and reports per-job completion so the window can react.

The worker is created via an injectable factory so the sequencing logic can be
unit-tested with a fake worker (no real separation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from ..config import Secrets, Settings
from ..models import JobRequest
from .worker import JobWorker

# Job lifecycle states.
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELED = "canceled"


@dataclass(slots=True)
class QueuedJob:
    """One entry in the queue."""

    id: int
    request: JobRequest
    label: str
    status: str = QUEUED
    detail: str = ""


class QueueController(QObject):
    """Runs queued jobs sequentially; one active at a time."""

    changed = Signal()                     # queue contents/status changed
    activeChanged = Signal(object)         # QueuedJob or None
    progress = Signal(object)              # ProgressEvent (active job)
    trackReady = Signal(object)            # Track (active job)
    analysisReady = Signal(object)         # AnalysisResult (active job)
    jobSucceeded = Signal(object, object)  # (QueuedJob, JobResult)
    jobFailed = Signal(object, str)        # (QueuedJob, message)
    jobCanceled = Signal(object)           # QueuedJob

    def __init__(
        self,
        settings: Settings,
        secrets: Optional[Secrets] = None,
        parent: Optional[QObject] = None,
        worker_factory: Optional[Callable[[JobRequest], object]] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._secrets = secrets
        self._jobs: list[QueuedJob] = []
        self._active: Optional[QueuedJob] = None
        self._worker = None
        self._next_id = 1
        self._factory = worker_factory or self._default_factory

    def _default_factory(self, request: JobRequest):
        return JobWorker(request, self._settings, self._secrets)

    # ----------------------------------------------------------- public API
    def jobs(self) -> list[QueuedJob]:
        return list(self._jobs)

    def active(self) -> Optional[QueuedJob]:
        return self._active

    def is_running(self) -> bool:
        return self._active is not None

    def add(self, request: JobRequest, label: str) -> QueuedJob:
        job = QueuedJob(id=self._next_id, request=request, label=label)
        self._next_id += 1
        self._jobs.append(job)
        self.changed.emit()
        self._start_next()
        return job

    def remove(self, job_id: int) -> None:
        """Remove a still-queued job (cannot remove the running one)."""
        for j in self._jobs:
            if j.id == job_id and j.status == QUEUED:
                self._jobs.remove(j)
                self.changed.emit()
                return

    def cancel(self, job_id: int) -> None:
        """Cancel the running job, or drop it if it is only queued."""
        if self._active and self._active.id == job_id and self._worker is not None:
            self._worker.cancel()
        else:
            self.remove(job_id)

    def clear_finished(self) -> None:
        before = len(self._jobs)
        self._jobs = [j for j in self._jobs if j.status in (QUEUED, RUNNING)]
        if len(self._jobs) != before:
            self.changed.emit()

    # --------------------------------------------------------------- engine
    def _start_next(self) -> None:
        if self._active is not None:
            return
        nxt = next((j for j in self._jobs if j.status == QUEUED), None)
        if nxt is None:
            self.activeChanged.emit(None)
            return

        self._active = nxt
        nxt.status = RUNNING
        worker = self._factory(nxt.request)
        self._worker = worker

        # Forward active-job streams.
        worker.progress.connect(self.progress)
        worker.trackReady.connect(self.trackReady)
        worker.analysisReady.connect(self.analysisReady)
        worker.succeeded.connect(lambda res, j=nxt: self._finish(j, DONE, res))
        worker.failed.connect(lambda msg, j=nxt: self._finish(j, FAILED, msg))
        worker.canceled.connect(lambda j=nxt: self._finish(j, CANCELED, None))

        self.changed.emit()
        self.activeChanged.emit(nxt)
        worker.start()

    def _finish(self, job: QueuedJob, status: str, payload) -> None:
        job.status = status
        if status == DONE:
            self.jobSucceeded.emit(job, payload)
        elif status == FAILED:
            job.detail = payload or ""
            self.jobFailed.emit(job, payload or "")
        elif status == CANCELED:
            self.jobCanceled.emit(job)

        self._active = None
        self._worker = None
        self.changed.emit()
        self._start_next()
