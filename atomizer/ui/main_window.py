"""Atomizer main window: wires the controls, worker, and result display."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __tagline__, __version__
from ..config import Secrets, Settings
from ..models import ExportFormat, JobRequest, ModelInfo
from .. import separator as separator_mod
from . import theme
from .widgets import DropZone, LogoLabel, MetricChip, NeonProgressBar
from .worker import JobWorker

# Optional audio preview (QtMultimedia ships with PySide6_Addons).
try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    _HAS_AUDIO = True
except Exception:  # pragma: no cover
    _HAS_AUDIO = False


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


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("Atomizer")
        self.resize(900, 980)

        self.settings = Settings.load()
        self.secrets = Secrets.from_env()
        self.worker: Optional[JobWorker] = None
        self._stem_boxes: dict[str, QCheckBox] = {}
        self._all_models = False
        self._player = None
        self._audio_out = None
        self._playing_path: Optional[str] = None

        self._build()
        self._populate_models()

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
        root.addWidget(self._build_progress_card())
        root.addWidget(self._build_analysis_card())
        root.addWidget(self._build_results_card())
        root.addStretch(1)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(LogoLabel("ATOMIZER"))
        tag = QLabel(__tagline__ + "   —   stem separation for Apple Silicon")
        tag.setObjectName("Muted")
        col.addWidget(tag)
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
        self.sr_label = QLabel("44.1 kHz")
        self.sr_label.setObjectName("Muted")
        row1.addWidget(self.sr_label)
        row1.addStretch(1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        from PySide6.QtWidgets import QLineEdit

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
        self.run_btn.clicked.connect(self._start)
        lay.addWidget(self.run_btn)
        return wrap

    def _build_progress_card(self) -> QFrame:
        card, lay = _card("Progress")
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
        self._last_folder: Optional[Path] = None
        return card

    # ------------------------------------------------------------ model UI
    def _populate_models(self) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        models = separator_mod.list_models(self.settings, recommended_only=not self._all_models)
        for m in models:
            prefix = "★ " if m.recommended else "   "
            self.model_combo.addItem(prefix + m.display_name, m)
        # Select the default model.
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
        # Clear existing checkboxes.
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

    def _start(self) -> None:
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
        req = JobRequest(
            source=source,
            model_filename=model.filename if model else self.settings.default_model,
            selected_stems=stems,
            export_format=ExportFormat(self.settings.export_format),
            bit_depth=self.settings.bit_depth,
            sample_rate=self.settings.sample_rate,
            output_dir=self.settings.output_path(),
            use_ensemble=self.ensemble_cb.isChecked(),
        )

        self._set_running(True)
        self.log.clear()
        self._clear_results()
        self.bpm_chip.set_value("—")
        self.key_chip.set_value("—")
        self.progress.set_busy(True)

        self.worker = JobWorker(req, self.settings, self.secrets, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.trackReady.connect(self._on_track)
        self.worker.analysisReady.connect(self._on_analysis)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(lambda: self._set_running(False))
        self.worker.start()

    def _set_running(self, running: bool) -> None:
        self.run_btn.setEnabled(not running)
        self.run_btn.setText("WORKING…" if running else "S E P A R A T E")
        if not running:
            self.progress.stop_pulse()

    # ------------------------------------------------------------- signals
    def _on_progress(self, message: str, frac: float) -> None:
        self.log.appendPlainText(message)
        if frac < 0:
            self.progress.set_busy(True)
        else:
            self.progress.stop_pulse()
            self.progress.set_progress(frac)

    def _on_track(self, track) -> None:
        if track.display_name:
            self.log.appendPlainText(f"   track: {track.display_name}")

    def _on_analysis(self, analysis) -> None:
        self.bpm_chip.set_value(analysis.bpm_text, analysis.bpm_source.value, analysis.bpm_confidence)
        self.key_chip.set_value(analysis.key_text, analysis.key_source.value, analysis.key_confidence)

    def _on_success(self, result) -> None:
        self.progress.stop_pulse()
        self.progress.set_progress(1.0)
        self._last_folder = result.export.folder
        self.open_btn.setEnabled(True)
        self._show_results(result)

    def _on_failed(self, message: str) -> None:
        self.progress.stop_pulse()
        self.progress.set_busy(False)
        self.progress.set_progress(0.0)
        self.log.appendPlainText(f"✗ ERROR: {message}")
        QMessageBox.critical(self, "Atomizer — error", message)

    # ------------------------------------------------------------- results
    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_results(self, result) -> None:
        self._clear_results()
        for stem in result.export.files:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            name = QLabel(stem.path.name)
            h.addWidget(name, 1)
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
