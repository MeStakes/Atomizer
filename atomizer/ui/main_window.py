"""Atomizer main window: wires the controls, job queue, and result display."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __tagline__, __version__
from ..config import Secrets, Settings
from ..models import ExportFormat, JobRequest, ModelInfo, ProgressEvent
from .. import separator as separator_mod
from . import theme
from .queue import CANCELED, DONE, FAILED, QUEUED, RUNNING, QueueController, QueuedJob
from .widgets import DropZone, LogoLabel, MetricChip, NeonProgressBar

# Optional audio preview (QtMultimedia ships with PySide6_Addons).
try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    _HAS_AUDIO = True
except Exception:  # pragma: no cover
    _HAS_AUDIO = False

_STATUS_COLOR = {
    QUEUED: theme.TEXT_MUTED,
    RUNNING: theme.PRIMARY,
    DONE: theme.ACCENT,
    FAILED: theme.DANGER,
    CANCELED: theme.TEXT_MUTED,
}
_STATUS_LABEL = {
    QUEUED: "queued",
    RUNNING: "running",
    DONE: "done",
    FAILED: "failed",
    CANCELED: "canceled",
}


def _card(title: Optional[str] = None) -> tuple[QFrame, QVBoxLayout]:
    """A rounded panel with an optional section title."""
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("SectionTitle")
        lay.addWidget(lbl)
    return frame, lay


def _short_source(source: str) -> str:
    """Compact label for a URL or file path."""
    if source.startswith(("http://", "https://")):
        return source if len(source) <= 46 else "…" + source[-45:]
    name = Path(source).name
    return name or source


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("Atomizer")
        self.resize(900, 1040)

        self.settings = Settings.load()
        self.secrets = Secrets.from_env()
        self._stem_boxes: dict[str, QCheckBox] = {}
        self._all_models = False
        self._player = None
        self._audio_out = None
        self._playing_path: Optional[str] = None
        self._last_folder: Optional[Path] = None
        self._last_eta: str = ""

        self._build()
        self._populate_models()

        self.controller = QueueController(self.settings, self.secrets, self)
        self.controller.changed.connect(self._refresh_queue)
        self.controller.activeChanged.connect(self._on_active_changed)
        self.controller.progress.connect(self._on_progress)
        self.controller.trackReady.connect(self._on_track)
        self.controller.analysisReady.connect(self._on_analysis)
        self.controller.jobSucceeded.connect(self._on_job_succeeded)
        self.controller.jobFailed.connect(self._on_job_failed)
        self.controller.jobCanceled.connect(self._on_job_canceled)
        self._refresh_queue()

    # ----------------------------------------------------------------- build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        body.setObjectName("Root")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 24, 28, 28)
        root.setSpacing(16)

        root.addLayout(self._build_header())
        root.addWidget(self._build_source_card())
        root.addWidget(self._build_model_card())
        root.addWidget(self._build_stems_card())
        root.addWidget(self._build_output_card())
        root.addWidget(self._build_run_button())
        root.addWidget(self._build_queue_card())
        root.addWidget(self._build_progress_card())
        root.addWidget(self._build_analysis_card())
        root.addWidget(self._build_results_card())
        root.addStretch(1)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(LogoLabel("ATOMIZER"))

        # Always-visible neon signature directly under the wordmark.
        sig = QLabel(
            f'by <span style="color:{theme.ACCENT};font-weight:700">&#9670; MeStakes</span>'
            f'<span style="color:{theme.TEXT_MUTED}">  &middot;  '
            f"{__tagline__} &mdash; stem separation for Apple Silicon</span>"
        )
        sig.setObjectName("Muted")
        sig.setTextFormat(Qt.TextFormat.RichText)
        sig_glow = QGraphicsDropShadowEffect(sig)
        sig_glow.setBlurRadius(14)
        sig_glow.setColor(QColor(theme.ACCENT))
        sig_glow.setOffset(0, 0)
        sig.setGraphicsEffect(sig_glow)
        col.addWidget(sig)
        row.addLayout(col)
        row.addStretch(1)
        about = QPushButton("About")
        about.setObjectName("Ghost")
        about.clicked.connect(self._about)
        row.addWidget(about, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _build_source_card(self) -> QFrame:
        card, lay = _card("Source")
        self.drop = DropZone()
        lay.addWidget(self.drop)
        return card

    def _build_model_card(self) -> QFrame:
        card, lay = _card("Separation model")
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        lay.addWidget(self.model_combo)

        self.model_desc = QLabel("")
        self.model_desc.setObjectName("ModelDesc")
        self.model_desc.setWordWrap(True)
        lay.addWidget(self.model_desc)

        row = QHBoxLayout()
        self.show_all_cb = QCheckBox("Show all models (163)")
        self.show_all_cb.toggled.connect(self._on_show_all)
        self.ensemble_cb = QCheckBox("Ensemble (max quality, ~2× slower)")
        self.ensemble_cb.toggled.connect(self._on_ensemble_toggled)
        row.addWidget(self.show_all_cb)
        row.addStretch(1)
        row.addWidget(self.ensemble_cb)
        lay.addLayout(row)
        return card

    def _build_stems_card(self) -> QFrame:
        card, lay = _card("Stems to export")
        hint = QLabel("Only the checked stems are written to disk.")
        hint.setObjectName("Hint")
        lay.addWidget(hint)
        self.stems_container = QVBoxLayout()
        self.stems_container.setSpacing(2)
        lay.addLayout(self.stems_container)
        return card

    def _build_output_card(self) -> QFrame:
        card, lay = _card("Output")
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(QLabel("Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["AIFF", "WAV"])
        self.format_combo.setCurrentText(self.settings.export_format)
        row1.addWidget(self.format_combo)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Bit depth"))
        self.depth_combo = QComboBox()
        self.depth_combo.addItems(["24", "16"])
        self.depth_combo.setCurrentText(str(self.settings.bit_depth))
        row1.addWidget(self.depth_combo)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Sample rate"))
        sr = QLabel("44.1 kHz")
        sr.setObjectName("Muted")
        row1.addWidget(sr)
        row1.addStretch(1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.out_edit = QLineEdit(self.settings.output_dir)
        self.out_edit.setPlaceholderText("~/Music/Atomizer")
        browse = QPushButton("Choose…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._choose_output)
        row2.addWidget(QLabel("Folder"))
        row2.addWidget(self.out_edit, 1)
        row2.addWidget(browse)
        lay.addLayout(row2)
        return card

    def _build_run_button(self) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 4, 0, 4)
        self.run_btn = QPushButton("S E P A R A T E")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setMinimumHeight(52)
        self.run_btn.clicked.connect(self._enqueue)
        lay.addWidget(self.run_btn)
        return wrap

    def _build_queue_card(self) -> QFrame:
        card, lay = _card("Queue")
        head = QHBoxLayout()
        self.queue_hint = QLabel("No jobs yet. Press SEPARATE to add one.")
        self.queue_hint.setObjectName("Hint")
        head.addWidget(self.queue_hint, 1)
        clear = QPushButton("Clear finished")
        clear.setObjectName("Ghost")
        clear.clicked.connect(lambda: self.controller.clear_finished())
        head.addWidget(clear)
        lay.addLayout(head)

        self.queue_layout = QVBoxLayout()
        self.queue_layout.setSpacing(6)
        lay.addLayout(self.queue_layout)
        return card

    def _build_progress_card(self) -> QFrame:
        card, lay = _card("Progress")
        self.status_line = QLabel("Idle.")
        self.status_line.setObjectName("Muted")
        lay.addWidget(self.status_line)
        self.progress = NeonProgressBar()
        lay.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        lay.addWidget(self.log)
        return card

    def _build_analysis_card(self) -> QFrame:
        card, lay = _card("Detected tempo & key")
        row = QHBoxLayout()
        row.setSpacing(14)
        self.bpm_chip = MetricChip("BPM")
        self.key_chip = MetricChip("Key")
        row.addWidget(self.bpm_chip, 1)
        row.addWidget(self.key_chip, 1)
        lay.addLayout(row)
        return card

    def _build_results_card(self) -> QFrame:
        card, lay = _card("Exported stems")
        self.results_layout = QVBoxLayout()
        self.results_layout.setSpacing(6)
        self.results_hint = QLabel("Results appear here after separation.")
        self.results_hint.setObjectName("Hint")
        self.results_layout.addWidget(self.results_hint)
        lay.addLayout(self.results_layout)

        self.open_btn = QPushButton("Open output folder")
        self.open_btn.setObjectName("Ghost")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_folder)
        lay.addWidget(self.open_btn)
        return card

    # ------------------------------------------------------------ model UI
    def _populate_models(self) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        models = separator_mod.list_models(self.settings, recommended_only=not self._all_models)
        for m in models:
            prefix = "★ " if m.recommended else "   "
            self.model_combo.addItem(prefix + m.display_name, m)
        for i in range(self.model_combo.count()):
            if self.model_combo.itemData(i).filename == self.settings.default_model:
                self.model_combo.setCurrentIndex(i)
                break
        self.model_combo.blockSignals(False)
        self._on_model_changed()

    def _current_model(self) -> Optional[ModelInfo]:
        data = self.model_combo.currentData()
        return data if isinstance(data, ModelInfo) else None

    def _on_show_all(self, checked: bool) -> None:
        self._all_models = checked
        self._populate_models()

    def _on_ensemble_toggled(self, checked: bool) -> None:
        self.model_combo.setEnabled(not checked)
        self.show_all_cb.setEnabled(not checked)
        if checked:
            self.model_desc.setText(
                "Ensemble: runs BS-Roformer + MelBand-Roformer and averages the "
                "vocal/instrumental stems. Falls back to the single best model if "
                "ensembling isn't possible."
            )
            self._rebuild_stems(["Vocals", "Instrumental"])
        else:
            self._on_model_changed()

    def _on_model_changed(self) -> None:
        m = self._current_model()
        if not m:
            return
        bits = [b for b in (m.architecture, m.quality) if b]
        self.model_desc.setText((m.description + ("   ·   " + " · ".join(bits) if bits else "")).strip())
        self._rebuild_stems(m.stems or ["Vocals", "Instrumental"])

    def _rebuild_stems(self, stems: list[str]) -> None:
        while self.stems_container.count():
            item = self.stems_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._stem_boxes.clear()
        for name in stems:
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.stems_container.addWidget(cb)
            self._stem_boxes[name] = cb

    def _selected_stems(self) -> list[str]:
        return [n for n, cb in self._stem_boxes.items() if cb.isChecked()]

    # ------------------------------------------------------------- actions
    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder", self.out_edit.text())
        if path:
            self.out_edit.setText(path)

    def _persist_settings(self) -> None:
        self.settings.export_format = self.format_combo.currentText()
        self.settings.bit_depth = int(self.depth_combo.currentText())
        self.settings.output_dir = self.out_edit.text().strip() or "~/Music/Atomizer"
        m = self._current_model()
        if m and not self.ensemble_cb.isChecked():
            self.settings.default_model = m.filename
        self.settings.save()

    def _enqueue(self) -> None:
        """Snapshot the form into a job and add it to the queue (auto-starts)."""
        source = self.drop.current_source()
        if not source:
            QMessageBox.warning(self, "Atomizer", "Paste a URL or choose an audio file first.")
            return
        stems = self._selected_stems()
        if not stems:
            QMessageBox.warning(self, "Atomizer", "Select at least one stem to export.")
            return

        self._persist_settings()
        model = self._current_model()
        use_ensemble = self.ensemble_cb.isChecked()
        req = JobRequest(
            source=source,
            model_filename=model.filename if model else self.settings.default_model,
            selected_stems=stems,
            export_format=ExportFormat(self.settings.export_format),
            bit_depth=self.settings.bit_depth,
            sample_rate=self.settings.sample_rate,
            output_dir=self.settings.output_path(),
            use_ensemble=use_ensemble,
        )
        model_label = "Ensemble" if use_ensemble else (model.display_name if model else self.settings.default_model)
        label = f"{_short_source(source)}  ·  {model_label}  ·  {', '.join(stems)}"
        self.controller.add(req, label)

    # ------------------------------------------------------------- queue UI
    def _refresh_queue(self) -> None:
        while self.queue_layout.count():
            item = self.queue_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        jobs = self.controller.jobs()
        self.queue_hint.setVisible(not jobs)
        for job in jobs:
            self.queue_layout.addWidget(self._queue_row(job))

    def _queue_row(self, job: QueuedJob) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {_STATUS_COLOR.get(job.status, theme.TEXT_MUTED)}; font-size: 13px;")
        h.addWidget(dot)

        text = QLabel(job.label)
        text.setToolTip(job.detail or job.label)
        h.addWidget(text, 1)

        status = QLabel(_STATUS_LABEL.get(job.status, job.status))
        status.setObjectName("Muted")
        status.setStyleSheet(f"color: {_STATUS_COLOR.get(job.status, theme.TEXT_MUTED)};")
        h.addWidget(status)

        if job.status == QUEUED:
            btn = QPushButton("✕")
            btn.setObjectName("Ghost")
            btn.setToolTip("Remove from queue")
            btn.clicked.connect(lambda _=False, jid=job.id: self.controller.remove(jid))
            h.addWidget(btn)
        elif job.status == RUNNING:
            btn = QPushButton("■ Cancel")
            btn.setObjectName("Ghost")
            btn.clicked.connect(lambda _=False, jid=job.id: self.controller.cancel(jid))
            h.addWidget(btn)
        return row

    # ------------------------------------------------------------- signals
    def _on_active_changed(self, job: Optional[QueuedJob]) -> None:
        if job is None:
            self.progress.stop_pulse()
            self.status_line.setText("Idle.")
            self.progress.set_busy(False)
            self.progress.set_progress(0.0)
        else:
            self._last_eta = ""
            self.log.appendPlainText(f"▶ Starting: {job.label}")
            self.progress.start_pulse()
            self.progress.set_busy(True)

    def _on_progress(self, ev: ProgressEvent) -> None:
        if ev.message:
            self.log.appendPlainText(ev.message)
        if ev.eta_sec is not None and ev.eta_sec > 0:
            self._last_eta = ev.eta_text

        pct = ev.overall_percent
        if pct is None:
            self.progress.set_busy(True)
            self.status_line.setText(f"{(ev.phase.title() or 'Working')}…")
            return

        self.progress.set_busy(False)
        self.progress.set_progress(ev.overall_fraction)
        phase = ev.phase.title() if ev.phase else "Working"
        seg = [phase, f"{pct}%"]
        if ev.phase in ("separation", "download") and self._last_eta:
            seg.append(f"ETA {self._last_eta}")
        self.status_line.setText("  ·  ".join(seg))

    def _on_track(self, track) -> None:
        if track.display_name:
            self.log.appendPlainText(f"   track: {track.display_name}")

    def _on_analysis(self, analysis) -> None:
        self.bpm_chip.set_value(analysis.bpm_text, analysis.bpm_source.value, analysis.bpm_confidence)
        self.key_chip.set_value(analysis.key_text, analysis.key_source.value, analysis.key_confidence)

    def _on_job_succeeded(self, job: QueuedJob, result) -> None:
        self.status_line.setText(f"✓ Done: {job.label}")
        self._last_folder = result.export.folder
        self.open_btn.setEnabled(True)
        self._show_results(result)

    def _on_job_failed(self, job: QueuedJob, message: str) -> None:
        self.log.appendPlainText(f"✗ ERROR [{job.label}]: {message}")
        self.status_line.setText(f"✗ Failed: {job.label}")

    def _on_job_canceled(self, job: QueuedJob) -> None:
        self.log.appendPlainText(f"■ Canceled: {job.label}")
        self.status_line.setText(f"■ Canceled: {job.label}")

    # ------------------------------------------------------------- results
    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_results(self, result) -> None:
        self._clear_results()
        header = QLabel(result.export.folder.name)
        header.setObjectName("Hint")
        self.results_layout.addWidget(header)
        for stem in result.export.files:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(QLabel(stem.path.name), 1)
            if _HAS_AUDIO:
                play = QPushButton("▶ Preview")
                play.setObjectName("Play")
                play.clicked.connect(lambda _=False, p=str(stem.path): self._toggle_play(p))
                h.addWidget(play)
            self.results_layout.addWidget(row)

    # ------------------------------------------------------------- preview
    def _ensure_player(self) -> None:
        if self._player is None and _HAS_AUDIO:
            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)

    def _toggle_play(self, path: str) -> None:
        if not _HAS_AUDIO:
            return
        self._ensure_player()
        if self._playing_path == path and self._player.isPlaying():
            self._player.stop()
            self._playing_path = None
            return
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self._playing_path = path

    def _open_folder(self) -> None:
        if self._last_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_folder)))

    # --------------------------------------------------------------- about
    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Atomizer",
            f"<b>Atomizer</b> v{__version__}<br>{__tagline__}<br><br>"
            "Local-first stem separation for Apple Silicon (MLX).<br>"
            "Models: BS-/MelBand-Roformer, HTDemucs. Audio never leaves your Mac "
            "(only optional BPM/key lookup uses the network).",
        )
