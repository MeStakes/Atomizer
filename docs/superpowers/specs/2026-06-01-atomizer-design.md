# Atomizer — Design Spec

**Date:** 2026-06-01
**Status:** Approved (build in progress)
**Target hardware:** MacBook Pro 16" 2021, Apple M1 Pro, 16 GB RAM, macOS Tahoe 26

## 1. Purpose

Atomizer is a **local-first desktop app** that "atomizes" a song into stems
(vocals, drums, bass, other, …) using the best open-source separation models,
optimized for Apple Silicon via MLX/Metal. It downloads audio from a URL
(YouTube, etc.) or a local file, separates the selected stems, detects BPM and
musical key, and exports files ready to drop into Apple **MainStage's Playback**
plugin.

**Hard constraints**
- Runs **locally and offline** for separation. Audio is **never uploaded** to any
  cloud service. Only BPM/key *lookup* may use the network.
- Uses **Apple Silicon GPU via MLX/Metal (MPS)**. **No CUDA assumptions.**
- Optimizes for **maximum separation quality**, not speed. Long processing is
  acceptable.

## 2. Tech stack

| Concern        | Choice                                                                 |
|----------------|------------------------------------------------------------------------|
| Separation     | `mlx-audio-separator[convert]` (MLX-native; Roformer/MDXC/MDX/VR/Demucs) |
| Download       | `yt-dlp` (best available audio, prefer lossless/opus)                  |
| BPM/key        | Online-first (GetSongBPM/Tunebat via API key in `.env`) → `librosa` fallback |
| Export         | `soundfile` + `ffmpeg` (AIFF/WAV, 24-bit/44.1 kHz)                      |
| UI             | **PySide6** (Qt), dark neon "cyber/sci-fi" theme via QSS               |
| Config         | `python-dotenv` + JSON settings file                                   |

PySide6 chosen over a pywebview web UI: native Qt, QSS theming, `QThread` for a
responsive UI during long jobs, `QPropertyAnimation` for the neon "pulse"
effects. No strong reason to prefer the web stack.

## 3. Models exposed (quality-first)

Populated **dynamically at runtime** from the library (`--list_models`) so the UI
never breaks if filenames change. A curated "recommended" subset is highlighted:

- **BS-Roformer** / **MelBand-Roformer** — best vocal/instrumental (SDX23 winners,
  ~12.9 dB SDR vocals). **Default at launch = highest-quality vocal model.**
- **HTDemucs FT** (`htdemucs_ft`) — full 4-stem (vocals/drums/bass/other).

**Ensemble:** not documented as native. Behaviour = graceful fallback to the
single best model, surfaced in the UI. *Stretch (optional):* manual
waveform-average ensemble only across models with identical stem taxonomy
(e.g. two vocal/instrumental Roformers). Averaging heterogeneous stems is not done.

## 4. Architecture (modules)

```
atomizer/
├── config.py       # settings + .env + paths + UI prefs persistence
├── models.py       # typed dataclasses: Track, StemSelection, AnalysisResult, ExportResult, ModelInfo
├── downloader.py   # yt-dlp: URL→audio (lossless/opus), title/artist metadata, progress; local-file passthrough
├── separator.py    # thin wrapper over mlx-audio-separator (verified against installed API); list_models(), separate(), progress, ensemble fallback
├── analysis.py     # BPM+key: online-first → librosa fallback (Krumhansl-Schmuckler key); reports source + confidence
├── exporter.py     # AIFF/WAV 24-bit/44.1, per-song folder, info.json, best-effort BPM metadata (WAV acid chunk)
├── pipeline.py     # orchestrates download→separate→analyze→export with progress callbacks (UI-agnostic)
├── ui/
│   ├── theme.qss        # neon cyber dark theme
│   ├── widgets.py       # URL/drag-drop input, model picker, stem checkboxes, neon progress, BPM/key panel, stem preview
│   ├── worker.py        # QThread worker wrapping pipeline; signals → UI
│   ├── main_window.py   # assembles the window
│   └── splash.py        # "ATOMIZER" splash/about
└── main.py         # entrypoint, splash, wiring
requirements.txt · README.md (Apple Silicon M1 Pro) · setup.sh (venv) · .env.example · .gitignore
```

Design principle: every module has one purpose, a typed interface, and is testable
in isolation. The `pipeline` is UI-agnostic so it can be unit-tested and reused
headless (CLI/end-to-end test).

## 5. Data flow

```
URL or local file
   → downloader      (audio file + {title, artist, …})
   → separator       (only the selected stems; emits per-step progress)
   → analysis        (BPM, key, source=online|local, confidence)
   → exporter        (MainStage-ready files + info.json in per-song folder)
```
Each stage reports real progress through the `QThread` worker → UI status log +
pulsing neon progress bar. Phases: download → separation → analysis → export.

## 6. UI requirements

- URL paste field **and** drag-and-drop / file picker for a local audio file.
- Model dropdown with per-model quality/speed description; default = best vocal model.
- Per-stem **checkboxes** (Vocals/Drums/Bass/Other, +Piano/Guitar when a 6-stem
  model is selected). **Only selected stems are exported.**
- "Separate" button → real progress bar + status log.
- BPM/key panel showing detected values, **source (online/local)** and **confidence**.
- Optional per-stem **preview playback** before export.
- Clear, **non-blocking** error handling.
- **First-run model download** shows progress in the UI (checkpoints can be 100s MB–GB).

## 7. Visual style

Cyber/sci-fi, neon on near-black. Palette: backgrounds `#0A0E14`–`#12161F`; accents
electric cyan `#00E5FF`, magenta/violet `#B14EFF`, aqua-green secondary. Neon
gradients, subtle glow/bloom on active elements, rounded corners, light glass
blur where sensible, smooth micro-animations on hover and during processing,
geometric tech sans typography (Inter / Space Grotesk; Orbitron for the logo).
Progress/processing states use a pulsing neon animation. Premium audio-tool feel,
while keeping high readability/contrast.

## 8. Export format (MainStage Playback)

MainStage's Playback supports uncompressed AIFF/WAV/CAF at 16/24-bit. `.aif` is
best (lower CPU, adjustable tempo info in the plugin).

- **Default: AIFF, stereo, 24-bit, 44.1 kHz** (WAV selectable as alternative).
- Folder per song: `Artist - Title (BPM - Key)/` with `01_Vocals.aif`,
  `02_Drums.aif`, … plus `info.json` (BPM, key, source, model, date).
- BPM in file metadata **best-effort** (AIFF annotation/comment; WAV `acid` chunk
  read by many hosts). The **guaranteed** channel is `info.json`, because
  MainStage-readable AIFF tempo embedding is not standardized.
- Output path configurable in the UI. **Default: `~/Music/Atomizer`.**

## 9. Error handling (non-blocking)

| Failure                         | Behaviour                                              |
|---------------------------------|--------------------------------------------------------|
| No network                      | Skip online lookup → local BPM/key, flagged in UI       |
| Download failed                 | Clear message, allow retry / different URL              |
| Model checkpoint missing        | Show download progress on first run                     |
| Optional dep (essentia) missing | Silent fallback to librosa                              |
| Separation error                | Logged in status panel; job stops without crashing UI   |

## 10. Testing

- Type hints + docstrings throughout; modules testable in isolation.
- **Unit tests** mock heavy deps (separator, yt-dlp, network) — fast, offline.
- **Real end-to-end test**: install deps, download one model, separate a short
  YouTube clip, verify exported files + info.json.

## 11. Project setup

- `requirements.txt` (complete), `README.md` titled **Atomizer** with step-by-step
  Apple Silicon M1 Pro install (ffmpeg via Homebrew; how to get/configure the
  BPM/key API key), and `setup.sh` to create the venv and install everything.
- First launch handles model checkpoint download/conversion with UI progress.

## 12. Open implementation note

The `mlx-audio-separator` README documents a minimal API
(`Separator().load_model(); separate(path)`). It is a port of upstream
`audio-separator`, whose API is richer (`output_dir`, `output_format`,
`output_single_stem`, `load_model(model_filename=...)`). `separator.py` is written
**against the actually installed API** (introspected post-install), not guessed,
and isolates all library calls behind a stable internal interface.
