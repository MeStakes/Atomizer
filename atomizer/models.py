"""Typed data structures shared across Atomizer modules.

These dataclasses define the stable interfaces between the downloader,
separator, analysis and exporter stages. Keeping them in one place lets every
module be reasoned about and tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


class AnalysisSource(str, Enum):
    """Where a BPM/key value came from."""

    ONLINE = "online"
    LOCAL = "local"
    UNKNOWN = "unknown"


class ExportFormat(str, Enum):
    """Supported export container/codec (uncompressed, MainStage-friendly)."""

    AIFF = "AIFF"
    WAV = "WAV"

    @property
    def extension(self) -> str:
        return ".aif" if self is ExportFormat.AIFF else ".wav"


@dataclass(slots=True)
class Track:
    """A source track: a local audio file plus whatever metadata we know.

    Produced by the downloader (from a URL) or built directly from a local file.
    """

    audio_path: Path
    title: Optional[str] = None
    artist: Optional[str] = None
    source_url: Optional[str] = None
    duration_sec: Optional[float] = None

    @property
    def display_name(self) -> str:
        """Human label, best-effort from available metadata."""
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        if self.title:
            return self.title
        return self.audio_path.stem


@dataclass(slots=True)
class ModelInfo:
    """A separation model exposed in the UI.

    ``filename`` is the identifier passed to the separator library.
    ``stems`` is the best-known list of stems the model produces (may be empty
    if unknown until the model runs).
    """

    filename: str
    display_name: str
    architecture: str = ""
    description: str = ""
    quality: str = ""  # short label e.g. "Highest", "High", "Good"
    recommended: bool = False
    stems: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StemResult:
    """One separated stem on disk (intermediate, pre-export)."""

    name: str  # e.g. "Vocals", "Drums"
    path: Path


@dataclass(slots=True)
class SeparationResult:
    """Output of the separator stage."""

    stems: list[StemResult]
    model: ModelInfo
    ensemble_used: bool = False
    note: str = ""  # e.g. "ensemble not supported, used best single model"

    def stem(self, name: str) -> Optional[StemResult]:
        for s in self.stems:
            if s.name.lower() == name.lower():
                return s
        return None


@dataclass(slots=True)
class AnalysisResult:
    """Detected BPM and musical key, with provenance."""

    bpm: Optional[float] = None
    key: Optional[str] = None  # e.g. "A minor"
    bpm_source: AnalysisSource = AnalysisSource.UNKNOWN
    key_source: AnalysisSource = AnalysisSource.UNKNOWN
    bpm_confidence: Optional[float] = None  # 0..1
    key_confidence: Optional[float] = None  # 0..1

    @property
    def bpm_text(self) -> str:
        return f"{self.bpm:.0f}" if self.bpm else "—"

    @property
    def key_text(self) -> str:
        return self.key or "—"


@dataclass(slots=True)
class ExportedStem:
    """A single exported, MainStage-ready file."""

    name: str
    path: Path


@dataclass(slots=True)
class ExportResult:
    """Output of the exporter stage."""

    folder: Path
    files: list[ExportedStem]
    info_path: Optional[Path] = None


@dataclass(slots=True)
class JobRequest:
    """Everything needed to run one end-to-end job.

    Built by the UI and consumed by the pipeline. Keeping it as a single value
    makes the pipeline easy to call headless (CLI / tests).
    """

    source: str  # URL or local file path
    model_filename: str
    selected_stems: list[str]  # subset of stems to export
    export_format: ExportFormat = ExportFormat.AIFF
    bit_depth: int = 24
    sample_rate: int = 44_100
    output_dir: Path = field(default_factory=lambda: Path.home() / "Music" / "Atomizer")
    use_ensemble: bool = False


def to_info_dict(
    track: Track,
    analysis: AnalysisResult,
    separation: SeparationResult,
    *,
    created_iso: str,
) -> dict:
    """Build the dict serialized into ``info.json`` next to exported stems."""
    return {
        "app": "Atomizer",
        "created": created_iso,
        "title": track.title,
        "artist": track.artist,
        "source_url": track.source_url,
        "bpm": analysis.bpm,
        "bpm_source": analysis.bpm_source.value,
        "bpm_confidence": analysis.bpm_confidence,
        "key": analysis.key,
        "key_source": analysis.key_source.value,
        "key_confidence": analysis.key_confidence,
        "model": separation.model.filename,
        "model_name": separation.model.display_name,
        "ensemble_used": separation.ensemble_used,
        "stems": [s.name for s in separation.stems],
    }


# Convenience for tests / serialization
def dataclass_to_dict(obj) -> dict:
    """Shallow-ish dataclass→dict that stringifies Paths and Enums."""

    def _clean(v):
        if isinstance(v, Path):
            return str(v)
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, list):
            return [_clean(x) for x in v]
        if hasattr(v, "__dataclass_fields__"):
            return {k: _clean(val) for k, val in asdict(v).items()}
        return v

    return {k: _clean(v) for k, v in asdict(obj).items()}
