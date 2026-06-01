"""Export separated stems as MainStage-ready files.

Writes uncompressed AIFF (default) or WAV at the configured bit depth and sample
rate, into a per-song folder, with clear numbered names, an ``info.json``
sidecar, and a best-effort BPM tempo chunk (WAV ``acid`` chunk).

The guaranteed metadata channel is ``info.json``; embedded tempo is best-effort
because MainStage-readable AIFF tempo embedding is not standardized.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import struct
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import soundfile as sf

from .config import Settings
from .models import (
    AnalysisResult,
    ExportedStem,
    ExportFormat,
    ExportResult,
    SeparationResult,
    Track,
    to_info_dict,
)

ProgressCallback = Callable[[str, Optional[float]], None]


def _noop(*_args, **_kwargs) -> None:
    pass


# Canonical stem ordering for numbered filenames.
_STEM_ORDER = ["vocals", "drums", "bass", "guitar", "piano", "other", "instrumental"]


def _sanitize(text: str) -> str:
    """Make a string safe for a file/folder name."""
    text = re.sub(r"[/\\:*?\"<>|]", "_", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:120] or "Unknown"


def _subtype_for(bit_depth: int) -> str:
    return {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}.get(bit_depth, "PCM_24")


def _stem_sort_key(name: str) -> tuple[int, str]:
    low = name.lower()
    try:
        return (_STEM_ORDER.index(low), low)
    except ValueError:
        return (len(_STEM_ORDER), low)


def folder_name(track: Track, analysis: AnalysisResult) -> str:
    """Build 'Artist - Title (BPM - Key)' (omitting unknown parts cleanly)."""
    name = track.display_name
    bpm = analysis.bpm_text
    key = analysis.key_text
    suffix_parts = [p for p in (f"{bpm} BPM" if analysis.bpm else "", key if analysis.key else "") if p]
    suffix = f" ({' - '.join(suffix_parts)})" if suffix_parts else ""
    return _sanitize(f"{name}{suffix}")


def _resample_if_needed(data: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr:
        return data
    import soxr

    return soxr.resample(data, sr, target_sr)


def _write_acid_chunk(wav_path: Path, bpm: float, n_frames: int, sample_rate: int) -> None:
    """Append a best-effort ACID 'acid' chunk carrying the tempo to a WAV file.

    Many DAWs/hosts read tempo from this chunk. Appending an extra chunk at the
    end of the RIFF is format-legal as long as the RIFF size is updated. Wrapped
    by the caller in try/except — failure must never break the export.
    """
    duration = n_frames / float(sample_rate)
    num_beats = max(1, int(round(duration * bpm / 60.0)))
    # ACID chunk payload (24 bytes): type, rootNote, unk1, unk2(float),
    # numBeats, meterDenom, meterNum, tempo(float).
    payload = struct.pack(
        "<IHHfIHHf",
        0,           # type flags: 0 = loop (tempo-based), not one-shot
        60,          # root note (middle C)
        0x8000,      # unknown1 (conventional)
        0.0,         # unknown2
        num_beats,   # number of beats
        4,           # meter denominator
        4,           # meter numerator
        float(bpm),  # tempo
    )
    chunk = b"acid" + struct.pack("<I", len(payload)) + payload

    raw = bytearray(wav_path.read_bytes())
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return  # not a RIFF/WAVE file; skip silently
    raw.extend(chunk)
    # Update RIFF chunk size (total file size - 8).
    new_riff_size = len(raw) - 8
    raw[4:8] = struct.pack("<I", new_riff_size)
    wav_path.write_bytes(bytes(raw))


# Note name (with sharp spelling) -> MIDI root in the 48..59 octave (C=48).
_NOTE_TO_MIDI = {
    "C": 48, "C#": 49, "D": 50, "D#": 51, "E": 52, "F": 53,
    "F#": 54, "G": 55, "G#": 56, "A": 57, "A#": 58, "B": 59,
}
# Flat -> enharmonic sharp spelling (or natural where applicable).
_FLAT_TO_SHARP = {
    "Cb": "B", "Db": "C#", "Eb": "D#", "Fb": "E",
    "Gb": "F#", "Ab": "G#", "Bb": "A#",
}


def _parse_key(key: Optional[str]) -> tuple[int, int]:
    """Parse a key string like 'F# major' / 'A minor' / 'Bb' / 'Am'.

    Returns ``(key_midi, scale)`` where key_midi is a MIDI root in 48..59 (or 0
    if unknown) and scale is 1=minor, 2=major, 3=neither/unknown.
    """
    if not key:
        return (0, 3)
    s = key.strip()
    if not s:
        return (0, 3)

    # Leading note letter A-G, optional accidental '#' or 'b'.
    m = re.match(r"^([A-Ga-g])([#b]?)", s)
    if not m:
        return (0, 3)
    letter = m.group(1).upper()
    accidental = m.group(2)
    note = letter + accidental
    if accidental == "b":
        note = _FLAT_TO_SHARP.get(letter + "b", letter)
    key_midi = _NOTE_TO_MIDI.get(note, 0)

    # Mode: minor if it mentions minor (and not major); else major.
    low = s.lower()
    is_minor = ("min" in low or re.search(r"\bm\b", low) is not None
                or low.endswith("m")) and "maj" not in low
    if is_minor:
        scale = 1
    else:
        scale = 2
    if key_midi == 0:
        scale = 3
    return (key_midi, scale)


def _write_basc_chunk(
    aiff_path: Path,
    bpm: float,
    key: Optional[str],
    n_frames: int,
    sample_rate: int,
) -> None:
    """Append a best-effort Apple Loops 'basc' chunk to an AIFF file.

    Apple Loops carry tempo/key in a ``basc`` chunk so hosts such as MainStage
    can auto-detect them. AIFF is big-endian and uses the ``FORM``/``AIFF``
    container, so (unlike the WAV ``acid`` chunk) the chunk is written
    big-endian and the FORM size is updated. Word-aligned per the AIFF spec.

    Wrapped by the caller in try/except — failure must never break the export.
    """
    duration_sec = n_frames / float(sample_rate)
    num_beats = max(1, int(round(duration_sec * bpm / 60.0)))
    key_midi, scale = _parse_key(key)

    # 84-byte payload (big-endian): loopable flag, numBeats, key root MIDI,
    # scale type, time sig numerator/denominator, then 68 filler zero bytes.
    payload = struct.pack(
        ">IIHHHH",
        1,          # loopable flag (always 1)
        num_beats,  # number of beats
        key_midi,   # MIDI root note (48..59) or 0 if unknown
        scale,      # 1=minor, 2=major, 3=neither/unknown
        4,          # time signature numerator
        4,          # time signature denominator
    ) + b"\x00" * 68
    chunk = b"basc" + struct.pack(">I", len(payload)) + payload

    raw = bytearray(aiff_path.read_bytes())
    if raw[0:4] != b"FORM" or raw[8:12] != b"AIFF":
        return  # not a FORM/AIFF file; skip silently
    if len(raw) % 2 == 1:
        raw.append(0)  # word-align before appending a new chunk
    raw.extend(chunk)
    # Update FORM chunk size (total file size - 8).
    raw[4:8] = struct.pack(">I", len(raw) - 8)
    aiff_path.write_bytes(bytes(raw))


def _write_audio(
    data: np.ndarray,
    sr: int,
    out_path: Path,
    fmt: ExportFormat,
    bit_depth: int,
    bpm: Optional[float],
    key: Optional[str] = None,
) -> None:
    """Write ``data`` to ``out_path`` in the target format/bit depth."""
    # Ensure stereo, float in [-1, 1].
    if data.ndim == 1:
        data = np.column_stack([data, data])
    elif data.shape[1] == 1:
        data = np.column_stack([data[:, 0], data[:, 0]])

    sf.write(
        str(out_path),
        data,
        sr,
        subtype=_subtype_for(bit_depth),
        format=fmt.value,  # "AIFF" or "WAV"
    )

    if bpm and fmt is ExportFormat.WAV:
        try:
            _write_acid_chunk(out_path, bpm, n_frames=data.shape[0], sample_rate=sr)
        except Exception:
            pass  # best-effort only

    if bpm and fmt is ExportFormat.AIFF:
        try:
            _write_basc_chunk(out_path, bpm, key, n_frames=data.shape[0], sample_rate=sr)
        except Exception:
            pass  # best-effort only


def export(
    separation: SeparationResult,
    track: Track,
    analysis: AnalysisResult,
    settings: Settings,
    selected_stems: Optional[list[str]] = None,
    progress: ProgressCallback = _noop,
) -> ExportResult:
    """Export the selected stems into a per-song folder. Returns paths written."""
    fmt = ExportFormat(settings.export_format)
    out_root = settings.output_path()
    folder = out_root / folder_name(track, analysis)
    folder.mkdir(parents=True, exist_ok=True)

    # Decide which stems to export.
    wanted = {s.lower() for s in selected_stems} if selected_stems else None
    stems = [s for s in separation.stems if (wanted is None or s.name.lower() in wanted)]
    stems.sort(key=lambda s: _stem_sort_key(s.name))

    files: list[ExportedStem] = []
    total = len(stems) or 1
    for i, stem in enumerate(stems, start=1):
        progress(f"Exporting {stem.name} ({i}/{len(stems)})…", i / total)
        data, sr = sf.read(str(stem.path), always_2d=True)
        data = _resample_if_needed(data, sr, settings.sample_rate)
        out_name = f"{i:02d}_{_sanitize(stem.name)}{fmt.extension}"
        out_path = folder / out_name
        _write_audio(data, settings.sample_rate, out_path, fmt, settings.bit_depth,
                     analysis.bpm, analysis.key)
        files.append(ExportedStem(name=stem.name, path=out_path))

    # info.json (guaranteed metadata channel).
    info = to_info_dict(track, analysis, separation,
                        created_iso=_dt.datetime.now().isoformat(timespec="seconds"))
    info["export_format"] = fmt.value
    info["bit_depth"] = settings.bit_depth
    info["sample_rate"] = settings.sample_rate
    info["exported_stems"] = [f.name for f in files]
    info_path = folder / "info.json"
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    progress(f"Export complete → {folder}", 1.0)
    return ExportResult(folder=folder, files=files, info_path=info_path)
