"""Configuration: secrets from .env, user settings persisted as JSON, paths.

Nothing here imports heavy libraries, so it is cheap to load at startup and
trivial to unit-test.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the current working directory / project root if present.
load_dotenv()

# Default model: the library's own default and the best vocal model available.
DEFAULT_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"

_APP_DIR_NAME = "Atomizer"


def _expand(p: str | os.PathLike) -> Path:
    """Expand ~ and environment variables into an absolute Path."""
    return Path(os.path.expanduser(os.path.expandvars(str(p)))).resolve()


def _settings_path() -> Path:
    """Where the JSON settings file lives (XDG-ish on macOS)."""
    base = Path(os.path.expanduser("~/Library/Application Support")) / _APP_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def _default_model_cache() -> Path:
    base = Path(os.path.expanduser("~/Library/Caches")) / _APP_DIR_NAME / "models"
    return base


@dataclass
class Settings:
    """User-facing, persisted settings. UI reads/writes these."""

    output_dir: str = "~/Music/Atomizer"
    download_dir: str = "~/Music/Atomizer/.cache/downloads"
    model_cache_dir: str = ""  # empty → _default_model_cache()
    export_format: str = "AIFF"  # AIFF | WAV
    bit_depth: int = 24
    sample_rate: int = 44_100
    default_model: str = DEFAULT_MODEL
    bpm_key_provider: str = "getsongbpm"  # getsongbpm | tunebat
    prefer_online_analysis: bool = True

    # --- resolved Paths (not persisted) ---
    def output_path(self) -> Path:
        p = _expand(self.output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def download_path(self) -> Path:
        p = _expand(self.download_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def model_cache_path(self) -> Path:
        p = _expand(self.model_cache_dir) if self.model_cache_dir else _default_model_cache()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # --- persistence ---
    def save(self) -> None:
        _settings_path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> "Settings":
        path = _settings_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass  # corrupt settings → fall back to defaults
        # Seed from environment if provided.
        s = cls()
        if env := os.getenv("ATOMIZER_OUTPUT_DIR"):
            s.output_dir = env
        if env := os.getenv("ATOMIZER_DOWNLOAD_DIR"):
            s.download_dir = env
        if env := os.getenv("BPM_KEY_PROVIDER"):
            s.bpm_key_provider = env
        return s


@dataclass(frozen=True)
class Secrets:
    """API keys for the optional online BPM/key lookup. Loaded from .env."""

    getsongbpm_api_key: Optional[str] = None
    tunebat_api_key: Optional[str] = None
    tunebat_api_host: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Secrets":
        def _clean(v: Optional[str]) -> Optional[str]:
            v = (v or "").strip()
            return v or None

        return cls(
            getsongbpm_api_key=_clean(os.getenv("GETSONGBPM_API_KEY")),
            tunebat_api_key=_clean(os.getenv("TUNEBAT_API_KEY")),
            tunebat_api_host=_clean(os.getenv("TUNEBAT_API_HOST")),
        )

    def has_online_provider(self) -> bool:
        return bool(self.getsongbpm_api_key or self.tunebat_api_key)
