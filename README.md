# Atomizer

> Atomize the sound. — Local-first audio **stem separation** for Apple Silicon.

Atomizer is a desktop app (PySide6) that splits a song into stems
(vocals, drums, bass, …) using the best open-source models, accelerated on
Apple Silicon via **MLX/Metal** — no CUDA, no cloud. It downloads audio from a
URL (YouTube, …) or a local file, detects **BPM** and **musical key**, and
exports files ready to drop into Apple **MainStage's Playback** plugin.

- **Separation:** [`mlx-audio-separator`](https://github.com/ssmall256/mlx-audio-separator) (BS-/MelBand-Roformer, HTDemucs, MDX, VR)
- **Download:** [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- **BPM/Key:** online lookup (GetSongBPM/Tunebat) → local [`librosa`](https://librosa.org) fallback (Krumhansl-Schmuckler)
- **Export:** AIFF/WAV, 24-bit/44.1 kHz, per-song folder + `info.json`

**Audio never leaves your Mac.** Only the optional BPM/key lookup uses the network.

---

## Requirements

- **Apple Silicon** Mac (M1/M2/M3/M4) — MLX requires it.
- **macOS 13+** (built and tested on macOS 26 / M1 Pro).
- **Python 3.10–3.12** (the app uses 3.12).
- **Homebrew** (for `ffmpeg`).

---

## Install (Apple Silicon, step-by-step)

### 1. ffmpeg (via Homebrew)

```bash
brew install ffmpeg
```

### 2. Python 3.12

```bash
brew install python@3.12        # if you don't already have it
```

### 3. One-shot setup

From the project folder:

```bash
./setup.sh
```

This creates a `.venv`, installs everything from `requirements.txt`, and copies
`.env.example` → `.env`.

<details>
<summary>Manual setup (equivalent)</summary>

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```
</details>

### 4. Run

```bash
source .venv/bin/activate
python -m atomizer.main
```

> **First run** downloads model checkpoints (100s MB – several GB depending on
> the model). Progress is shown in the app's status log. Checkpoints are cached
> under `~/Library/Caches/Atomizer/models`.

---

## BPM / Key online lookup (optional)

Atomizer tries an online provider first (using the track title + artist from
yt-dlp), then falls back to local analysis. **No key = it just uses local
analysis** — everything still works.

Edit `.env`:

```ini
# GetSongBPM (free, requires an attribution backlink on your site):
#   https://getsongbpm.com/api
GETSONGBPM_API_KEY=your_key_here

# or Tunebat via RapidAPI:
TUNEBAT_API_KEY=your_rapidapi_key
TUNEBAT_API_HOST=tunebat-api.p.rapidapi.com

# Which to try first:
BPM_KEY_PROVIDER=getsongbpm
```

The UI always shows whether a value came from **online** or **local**, with a
confidence estimate.

---

## Using the app

1. **Paste a URL** or **drop / choose** a local audio file.
2. Pick a **separation model** (default = BS-Roformer, best vocals). Toggle
   *Show all models* for the full 163-model catalogue, or *Ensemble* for max
   quality.
3. Check the **stems** you want exported (only checked ones are written).
4. Choose **format** (AIFF default / WAV), **bit depth** (24/16), and the
   **output folder** (default `~/Music/Atomizer`).
5. Hit **SEPARATE**. The job is added to the **Queue** and starts immediately if
   nothing else is running.
6. **Queue more while one runs** — change the form and press SEPARATE again;
   jobs run one at a time. Remove queued jobs or **Cancel** the running one
   (cancel takes effect at the next inference chunk).
7. The **progress bar shows a real percentage and ETA** during separation; BPM/key
   fill in automatically.
8. **Preview** each stem and **Open output folder** when done.

### Output layout

```
~/Music/Atomizer/
└── Artist - Title (128 BPM - A minor)/
    ├── 01_Vocals.aif
    ├── 02_Drums.aif
    ├── 03_Bass.aif
    ├── 04_Other.aif
    └── info.json        # BPM, key, source, model, date
```

For WAV exports, the detected tempo is also written into an `acid` chunk
(read by many DAWs). For AIFF, tempo lives in `info.json` (the reliable channel),
since MainStage-readable AIFF tempo embedding isn't standardized.

---

## Recommended models

| Model | Stems | Notes |
|-------|-------|-------|
| **BS-Roformer** (default) | Vocals / Instrumental | SDX23 winner, ~12.9 dB SDR vocals. Highest quality, slowest. |
| **MelBand-Roformer** | Vocals / Instrumental | Excellent alternative. |
| **HTDemucs FT** | Vocals / Drums / Bass / Other | Full 4-stem split. |
| **HTDemucs 6s** | + Guitar / Piano | 6-stem split. |

Speed is **not** a priority — Atomizer favours quality. Long jobs are normal.

---

## Project structure

```
atomizer/
├── config.py       # settings, .env, paths
├── models.py       # typed dataclasses
├── downloader.py   # yt-dlp
├── separator.py    # mlx-audio-separator wrapper + ensemble fallback
├── analysis.py     # BPM/key online + local
├── exporter.py     # AIFF/WAV + info.json + tempo metadata
├── pipeline.py     # end-to-end orchestration (UI-agnostic)
├── ui/             # PySide6 neon UI
└── main.py         # entrypoint
```

---

## Troubleshooting

- **`essentia` install fails on Apple Silicon** — it's optional. Atomizer uses
  `librosa` for local analysis and never requires essentia.
- **YouTube download fails** — update yt-dlp: `pip install -U yt-dlp`. Some
  videos are region/bot restricted; try another URL or a local file.
- **Model download is slow** — checkpoints are large and downloaded once, then
  cached. Subsequent runs reuse them.
- **No GPU acceleration** — ensure you're on Apple Silicon; MLX uses Metal
  automatically.

---

## Notes

- All separation runs locally and offline.
- Built and verified on MacBook Pro 16" 2021 (M1 Pro, 16 GB), macOS 26.
