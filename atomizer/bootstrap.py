"""First-run bootstrap: pre-download the recommended model checkpoints.

Run after installing dependencies so the app is ready to separate offline with
no first-use wait:

    python -m atomizer.bootstrap            # download all recommended models
    python -m atomizer.bootstrap --list     # just list what would be downloaded
    python -m atomizer.bootstrap a.ckpt ...  # download specific model files

Checkpoints are cached under ~/Library/Caches/Atomizer/models and are reused on
every later run (they survive reboots).
"""

from __future__ import annotations

import sys
from typing import Iterable, Optional

from .config import Settings
from . import separator


def recommended_filenames(settings: Optional[Settings] = None) -> list[str]:
    """Filenames of the curated, quality-first recommended models."""
    settings = settings or Settings.load()
    return [m.filename for m in separator.list_models(settings, recommended_only=True)]


def prefetch_models(
    filenames: Optional[Iterable[str]] = None,
    settings: Optional[Settings] = None,
) -> tuple[list[str], list[str]]:
    """Download the given (or all recommended) models. Returns (ok, failed)."""
    settings = settings or Settings.load()
    targets = list(filenames) if filenames else recommended_filenames(settings)
    ok: list[str] = []
    failed: list[str] = []
    total = len(targets)
    for i, fname in enumerate(targets, start=1):
        print(f"[{i}/{total}] {fname}", flush=True)
        try:
            separator.ensure_model(settings, fname, lambda *a, **k: None)
            ok.append(fname)
            print(f"      ✓ ready", flush=True)
        except Exception as exc:  # keep going; one bad model shouldn't abort
            failed.append(fname)
            print(f"      ✗ {exc}", flush=True)
    return ok, failed


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    settings = Settings.load()

    if "--list" in argv:
        print("Recommended models:")
        for f in recommended_filenames(settings):
            print(f"  - {f}")
        print(f"\nCache dir: {settings.model_cache_path()}")
        return 0

    explicit = [a for a in argv if not a.startswith("-")]
    print("Atomizer — pre-downloading models (first time can be several GB)…")
    print(f"Cache dir: {settings.model_cache_path()}\n")
    ok, failed = prefetch_models(explicit or None, settings)
    print(f"\nDone. {len(ok)} ready, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
