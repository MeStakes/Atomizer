<div align="center">

# ⚡ ATOMIZER

**Atomizza il suono.** — **Separazione di stem audio** in locale per Apple Silicon.

[🇬🇧 English](README.md)  ·  **🇮🇹 Italiano**

![Platform](https://img.shields.io/badge/platform-Apple%20Silicon-111?logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![MLX](https://img.shields.io/badge/accel-MLX%20%2F%20Metal-FF6A00)
![UI](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-00E5FF)

Separa qualsiasi canzone in stem (voce, batteria, basso, …) con i migliori modelli
open-source, accelerati su Apple Silicon via **MLX/Metal**. Scarica da un URL o da
un file locale, rileva **BPM** e **tonalità**, ed esporta file pronti per il plugin
**Playback** di Apple **MainStage**.

<sub>Niente cloud. Niente CUDA. Il tuo audio non lascia mai il Mac.</sub>

<br>

<img src="assets/atomizer-ui.png" alt="Interfaccia Atomizer" width="720">

</div>

---

## ✨ Funzionalità

- 🎚️ **Separazione di altissimo livello** — BS-Roformer & MelBand-Roformer
  (vincitori SDX23), HTDemucs FT (4 stem) e HTDemucs 6s (+chitarra/piano). 163
  modelli in tutto.
- 🍎 **Nativo Apple Silicon** — gira sulla GPU via MLX/Metal. Niente PyTorch/ONNX
  all'inferenza, niente CUDA.
- 🔗 **URL o file** — incolla un link (YouTube, ecc.) o trascina un file locale.
- 🥁 **Scegli gli stem** — esporta solo quelli che spunti.
- 🎼 **Rilevamento BPM + tonalità** — lookup online prima (API key opzionale),
  fallback locale automatico (librosa / Krumhansl-Schmuckler). Mostra sempre fonte
  e confidenza.
- 📋 **Coda di job** — avvia una separazione e accodane altre mentre gira; annulla
  o rimuovi quando vuoi.
- 📊 **Progress reale + ETA** — percentuale vera per-chunk e tempo rimanente durante
  l'inferenza.
- 🎧 **Anteprima ed export** — ascolta gli stem, poi esporta **AIFF/WAV 24-bit/44.1
  kHz** in una cartella ordinata per canzone con `info.json`.
- 🎯 **Metadati pronti per MainStage** — gli export AIFF includono un chunk Apple
  Loops `basc` (tempo + tonalità) così MainStage può auto-rilevarli; il WAV ha un
  chunk `acid` col tempo; `info.json` è sempre presente.
- 🌃 **UI neon cyber** — interfaccia PySide6 scura e futuristica.
- 🔒 **Privato** — la separazione è interamente locale/offline; solo il lookup
  opzionale BPM/tonalità usa la rete.

---

## 🚀 Avvio rapido

> **Requisiti:** Mac Apple Silicon (M1/M2/M3/M4), macOS 13+, [Homebrew](https://brew.sh).

### Opzione A — con git

```bash
git clone https://github.com/MeStakes/Atomizer.git
cd Atomizer
./setup.sh
source .venv/bin/activate
python -m atomizer.main
```

### Opzione B — senza git (scarica lo ZIP)

1. Apri **https://github.com/MeStakes/Atomizer** → pulsante verde **Code** → **Download ZIP**
   (oppure usa il [link diretto](https://github.com/MeStakes/Atomizer/archive/refs/heads/main.zip)).
2. Fai doppio click sul file `Atomizer-main.zip` scaricato per estrarlo (es. in *Download*).
3. Apri l'app **Terminale** ed esegui:

```bash
cd ~/Downloads/Atomizer-main      # la cartella estratta
bash setup.sh
source .venv/bin/activate
python -m atomizer.main
```

> Suggerimento: se non hai ancora Homebrew, incolla prima questo nel Terminale:
> `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`

In entrambi i casi, `setup.sh` fa tutto:

1. installa **ffmpeg** (Homebrew),
2. crea un **virtualenv Python 3.12** e installa tutte le dipendenze,
3. crea `.env` dal template,
4. **pre-scarica i modelli consigliati**, così l'app è pronta a separare offline
   senza attese al primo utilizzo.

> Il download dei modelli è di qualche GB **solo la prima volta** — i checkpoint
> restano in cache in `~/Library/Caches/Atomizer/models` e vengono riusati per
> sempre (sopravvivono ai riavvii). Per saltarlo e farli scaricare alla bisogna:
> `./setup.sh --no-models`.

Pre-scarica (o completa) i modelli quando vuoi:

```bash
python -m atomizer.bootstrap          # tutti i modelli consigliati
python -m atomizer.bootstrap --list   # mostra cosa verrebbe scaricato
```

---

## 🎛️ Come si usa

1. **Incolla un URL** oppure **trascina / scegli** un file audio locale.
2. Scegli un **modello di separazione** (default = BS-Roformer, miglior voce).
   Attiva *Show all models* per il catalogo completo, o *Ensemble* per la massima
   qualità (esegue due modelli e ne fa la media).
3. Spunta gli **stem** da esportare — solo quelli spuntati vengono scritti.
4. Scegli **formato** (AIFF default / WAV), **bit depth** (24/16) e la **cartella
   di output** (default `~/Music/Atomizer`).
5. Premi **SEPARATE** — il job entra nella **coda** e parte subito se è libera.
6. **Accoda altri job mentre uno gira**: cambia i campi e ripremi SEPARATE. Vengono
   eseguiti uno alla volta. **Annulla** quello in corso (si ferma al chunk
   successivo) o **✕** rimuovi uno in coda.
7. Guarda la **% reale + ETA** durante la separazione; BPM/tonalità si compilano da
   soli con fonte (online/locale) e confidenza.
8. **Ascolta** ogni stem e **apri la cartella di output** alla fine.

### Struttura dell'output

```
~/Music/Atomizer/
└── Negrita - Magnolia (170 BPM - F# major)/
    ├── 01_Vocals.aif        # AIFF, stereo, 24-bit, 44.1 kHz
    ├── 02_Instrumental.aif
    └── info.json            # bpm, tonalità, fonte, modello, data
```

---

## 🎹 Modelli consigliati

| Modello | Stem | Note |
|---------|------|------|
| **BS-Roformer** *(default)* | Voce / Strumentale | Vincitore SDX23, ~12.9 dB SDR voce. Qualità massima. |
| **MelBand-Roformer** | Voce / Strumentale | Ottima alternativa. |
| **HTDemucs FT** | Voce / Batteria / Basso / Altro | Split completo a 4 stem. |
| **HTDemucs 6s** | + Chitarra / Piano | Split a 6 stem. |
| *Ensemble* | Voce / Strumentale | Esegue BS + MelBand e media — qualità massima, ~2× più lento. |

Atomizer privilegia la **qualità sulla velocità** — i job lunghi sono normali.

---

## 🔑 Opzionale: lookup BPM / tonalità online

Atomizer rileva BPM/tonalità in locale già di suo. Per un lookup online (spesso più
veloce e accurato), aggiungi una chiave in `.env`:

```ini
# GetSongBPM (gratis, richiede un backlink di attribuzione): https://getsongbpm.com/api
GETSONGBPM_API_KEY=la_tua_chiave

# oppure Tunebat via RapidAPI:
TUNEBAT_API_KEY=la_tua_chiave_rapidapi
TUNEBAT_API_HOST=tunebat-api.p.rapidapi.com

BPM_KEY_PROVIDER=getsongbpm   # quale provare per primo
```

Nessuna chiave → usa semplicemente l'analisi locale. La UI indica sempre da quale
fonte arriva ogni valore.

---

## 🧱 Struttura del progetto

```
atomizer/
├── config.py       # impostazioni, .env, percorsi
├── models.py       # dataclass tipizzate + ProgressEvent
├── downloader.py   # yt-dlp
├── separator.py    # wrapper mlx-audio-separator, catalogo modelli, ensemble, progress live
├── analysis.py     # BPM/tonalità (online + locale)
├── exporter.py     # AIFF/WAV + info.json
├── pipeline.py     # orchestrazione end-to-end (indipendente dalla UI)
├── bootstrap.py    # pre-download modelli
├── ui/             # UI PySide6 neon + coda job
└── main.py         # entrypoint
```

---

## 🧪 Sviluppo

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen pytest -q       # esegue i test
```

---

## 🛠️ Risoluzione problemi

- **`essentia` non si installa su Apple Silicon** — è opzionale; Atomizer usa
  `librosa` e non lo richiede mai.
- **Il download da YouTube fallisce** — aggiorna yt-dlp (`pip install -U yt-dlp`);
  alcuni video sono limitati per regione/bot — prova un altro URL o un file locale.
- **La prima separazione è lenta** — il checkpoint si scarica una volta sola (esegui
  prima `python -m atomizer.bootstrap` per evitare l'attesa), poi resta in cache.
- **Niente accelerazione GPU** — assicurati di essere su Apple Silicon; MLX usa
  Metal automaticamente.

---

## 📝 Note

- La separazione gira interamente in locale e offline.
- Costruito e verificato su MacBook Pro 16" (M1 Pro, 16 GB), macOS 26.
- Basato su [mlx-audio-separator](https://github.com/ssmall256/mlx-audio-separator),
  [yt-dlp](https://github.com/yt-dlp/yt-dlp), [librosa](https://librosa.org) e
  [PySide6](https://doc.qt.io/qtforpython/).
