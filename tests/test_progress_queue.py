"""Tests for the progress/ETA machinery and the sequential job queue."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from atomizer import separator
from atomizer.config import Settings
from atomizer.models import JobCancelled, JobRequest, ProgressEvent, format_eta
from atomizer.pipeline import PHASE_WEIGHTS, _phase_base


# ----------------------------------------------------------------- ETA / event
def test_format_eta():
    assert format_eta(None) == "—"
    assert format_eta(-3) == "—"
    assert format_eta(0) == "00:00"
    assert format_eta(75) == "01:15"
    assert format_eta(3725) == "1:02:05"


def test_progress_event_properties():
    ev = ProgressEvent("hi", "separation", phase_fraction=0.5, overall_fraction=0.5, eta_sec=30)
    assert ev.overall_percent == 50
    assert ev.eta_text == "00:30"
    blank = ProgressEvent("x")
    assert blank.overall_percent is None
    assert blank.eta_text == "—"


# ------------------------------------------------------------- phase weighting
def test_phase_weights_sum_to_one():
    assert abs(sum(PHASE_WEIGHTS.values()) - 1.0) < 1e-9


def test_phase_base_cumulative():
    assert _phase_base("download") == 0.0
    assert abs(_phase_base("separation") - PHASE_WEIGHTS["download"]) < 1e-9
    expected = PHASE_WEIGHTS["download"] + PHASE_WEIGHTS["separation"] + PHASE_WEIGHTS["analysis"]
    assert abs(_phase_base("export") - expected) < 1e-9


# --------------------------------------------------------------- patched tqdm
def test_patched_tqdm_reports_fractions():
    events = []
    prog = lambda msg, frac=None, eta=None: events.append((frac, eta))
    patched = separator._make_patched_tqdm(prog, None)
    out = list(patched(range(4), total=4, desc="MLX inference"))
    assert out == [0, 1, 2, 3]
    assert [round(e[0], 3) for e in events] == [0.25, 0.5, 0.75, 1.0]
    assert all(e[1] is not None and e[1] >= 0 for e in events)


def test_patched_tqdm_ignores_non_inference_bars():
    events = []
    patched = separator._make_patched_tqdm(lambda *a, **k: events.append(a), None)
    out = list(patched(range(3), total=3, desc="Loading bands"))
    assert out == [0, 1, 2]
    assert events == []  # only "inference" bars report


def test_patched_tqdm_cancels():
    patched = separator._make_patched_tqdm(lambda *a, **k: None, lambda: True)
    with pytest.raises(JobCancelled):
        next(iter(patched(range(5), total=5, desc="MLX inference")))


# ------------------------------------------------------------------- the queue
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _make_fake_worker_cls():
    from PySide6.QtCore import QObject, Signal

    class FakeWorker(QObject):
        progress = Signal(object)
        trackReady = Signal(object)
        analysisReady = Signal(object)
        succeeded = Signal(object)
        failed = Signal(str)
        canceled = Signal()

        def __init__(self, request):
            super().__init__()
            self.request = request
            self.started = False
            self.cancel_called = False

        def cancel(self):
            self.cancel_called = True
            self.canceled.emit()

        def start(self):
            self.started = True

    return FakeWorker


def _controller(workers):
    from atomizer.ui.queue import QueueController

    Fake = _make_fake_worker_cls()

    def factory(req):
        w = Fake(req)
        workers.append(w)
        return w

    return QueueController(Settings(), None, worker_factory=factory)


def _req():
    return JobRequest(source="x.wav", model_filename="m", selected_stems=["Vocals"])


def test_queue_runs_sequentially(qapp):
    workers = []
    ctrl = _controller(workers)
    j1 = ctrl.add(_req(), "j1")
    j2 = ctrl.add(_req(), "j2")

    # First runs, second waits.
    assert j1.status == "running"
    assert j2.status == "queued"
    assert ctrl.active() is j1
    assert len(workers) == 1

    workers[0].succeeded.emit("RESULT1")
    # First done, second now running.
    assert j1.status == "done"
    assert j2.status == "running"
    assert len(workers) == 2

    workers[1].succeeded.emit("RESULT2")
    assert j2.status == "done"
    assert ctrl.active() is None


def test_queue_remove_queued(qapp):
    workers = []
    ctrl = _controller(workers)
    j1 = ctrl.add(_req(), "j1")
    j2 = ctrl.add(_req(), "j2")
    ctrl.remove(j2.id)
    assert all(j.id != j2.id for j in ctrl.jobs())
    # Cannot remove the running one.
    ctrl.remove(j1.id)
    assert any(j.id == j1.id for j in ctrl.jobs())


def test_queue_cancel_running(qapp):
    workers = []
    ctrl = _controller(workers)
    j1 = ctrl.add(_req(), "j1")
    ctrl.cancel(j1.id)
    assert workers[0].cancel_called
    assert j1.status == "canceled"
    assert ctrl.active() is None


def test_queue_failure_continues(qapp):
    workers = []
    ctrl = _controller(workers)
    j1 = ctrl.add(_req(), "j1")
    j2 = ctrl.add(_req(), "j2")
    workers[0].failed.emit("boom")
    assert j1.status == "failed"
    assert j1.detail == "boom"
    assert j2.status == "running"
