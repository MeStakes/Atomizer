"""Download source audio from a URL via yt-dlp, or accept a local file.

Always extracts the best available audio and produces a lossless WAV that the
separator can consume directly, plus best-effort title/artist metadata used for
the online BPM/key lookup.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Optional

from .models import Track

# (message, fraction 0..1 or None for indeterminate)
ProgressCallback = Callable[[str, Optional[float]], None]

_AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".opus", ".ogg", ".wma"}


def _noop(_msg: str, _frac: Optional[float]) -> None:
    pass


def is_url(source: str) -> bool:
    """True if ``source`` looks like an http(s) URL rather than a file path."""
    return bool(re.match(r"^https?://", source.strip(), re.IGNORECASE))


def _split_artist_title(info: dict) -> tuple[Optional[str], Optional[str]]:
    """Best-effort artist/title from yt-dlp metadata.

    Prefers music-specific fields (artist/track), then falls back to parsing a
    "Artist - Title" video title.
    """
    artist = info.get("artist") or info.get("creator") or info.get("uploader")
    title = info.get("track") or info.get("title")

    raw_title = info.get("title") or ""
    if (not info.get("artist") and not info.get("track")) and " - " in raw_title:
        left, right = raw_title.split(" - ", 1)
        artist = left.strip()
        # strip trailing "(Official Video)" etc. from the title part
        title = re.sub(r"\s*[\(\[].*?(official|video|audio|lyric).*?[\)\]]\s*$", "", right,
                       flags=re.IGNORECASE).strip() or right.strip()

    return (artist.strip() if artist else None, title.strip() if title else None)


def track_from_local_file(path: str | os.PathLike) -> Track:
    """Build a :class:`Track` from an existing local audio file."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {p}")
    if p.suffix.lower() not in _AUDIO_EXTS:
        raise ValueError(f"Unsupported audio file type: {p.suffix}")
    # Try to parse "Artist - Title" from the filename.
    artist, title = None, p.stem
    if " - " in p.stem:
        left, right = p.stem.split(" - ", 1)
        artist, title = left.strip(), right.strip()
    return Track(audio_path=p, title=title, artist=artist, source_url=None)


def download(
    url: str,
    output_dir: str | os.PathLike,
    progress: ProgressCallback = _noop,
) -> Track:
    """Download the best audio for ``url`` into ``output_dir`` as lossless WAV.

    Returns a :class:`Track` with the resulting file path and parsed metadata.
    Raises ``RuntimeError`` on download failure (with a readable message).
    """
    import yt_dlp  # lazy: keeps module import cheap

    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    captured: dict = {}

    def hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            frac = (done / total) if total else None
            mb = done / 1_048_576
            progress(f"Downloading audio… {mb:.1f} MB", frac)
        elif status == "finished":
            progress("Download complete, extracting audio…", None)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        # Extract to lossless WAV so the separator gets a clean input.
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "0"}
        ],
    }

    progress("Resolving URL…", None)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            captured.update(info)
    except Exception as exc:  # yt_dlp raises various subclasses
        raise RuntimeError(f"Download failed: {exc}") from exc

    # Resolve the produced .wav path (postprocessor changes the extension).
    audio_id = captured.get("id", "")
    wav_path = out / f"{audio_id}.wav"
    if not wav_path.exists():
        # Fall back to whatever file id.* exists.
        candidates = sorted(out.glob(f"{audio_id}.*"))
        candidates = [c for c in candidates if c.suffix.lower() in _AUDIO_EXTS]
        if not candidates:
            raise RuntimeError("Download succeeded but no audio file was produced.")
        wav_path = candidates[0]

    artist, title = _split_artist_title(captured)
    return Track(
        audio_path=wav_path,
        title=title,
        artist=artist,
        source_url=url,
        duration_sec=captured.get("duration"),
    )


def resolve_source(
    source: str,
    output_dir: str | os.PathLike,
    progress: ProgressCallback = _noop,
) -> Track:
    """Dispatch: download if ``source`` is a URL, else treat it as a local file."""
    if is_url(source):
        return download(source, output_dir, progress)
    progress("Loading local file…", None)
    return track_from_local_file(source)
