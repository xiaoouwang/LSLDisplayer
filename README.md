# Multimodal LSL Explorer

Web-based viewer and Python helpers for exploring synchronized recordings exported from [Lab Streaming Layer (LSL)](https://labstreaminglayer.org/#/) `.xdf` files. Developed at **CoCoLab** (Université Côte d'Azur / MSHS Sud-Est) for multimodal experiments combining PsychoPy, input devices, audio, and other LSL streams.

**Interface:** [Xiaoou Wang](https://xiaoouwang.github.io/) · Ingénieur en Humanités Numériques · MSHS Sud-Est

---

[Web Interface](https://xiaoouwang.github.io/LSLDisplayer/)

## Context

This work supports internships at CoCoLab (supervised by Noelia and the CoCoLab team), connecting and synchronizing multiple signal sources — e.g. frontal camera video, screen capture, Tobii eye-tracking — via LSL. LSL records to `.xdf`, enabling multimodal databases with a shared clock across streams.

---

## Project layout

```
explorer/
├── index.html              # Main web explorer (static, no build step)
├── static/                 # Logos (CoCoLab, LSL, PsychoPy, partners)
├── exports/                # Demo export folder (loaded automatically on open)
│   ├── manifest.json       # Session metadata and stream index
│   ├── 1_MousePosition.csv
│   ├── 2_Keyboard.csv
│   ├── 3_PsychoPy.csv
│   ├── 4_MouseButtons.csv
│   └── 5_MyAudioStream.wav
├── demo.py                 # Export an .xdf file to CSV/WAV + manifest
├── inspect_streams.py      # Generate an HTML metadata report from .xdf
└── README.md
```

Place your source `.xdf` file next to `demo.py` (default name: `newtest.xdf`) before exporting.

---

## Requirements

Python 3 with:

- `pyxdf`
- `numpy`
- `pandas`

Install:

```bash
pip install pyxdf numpy pandas
```

The web explorer runs in a modern browser. It must be served over HTTP (not opened as `file://`) so the built-in demo can load `exports/`.

---

## Quick start — web explorer

From the `explorer` folder:

```bash
python -m http.server 8000
```

Open [http://localhost:8000/](http://localhost:8000/) or the [hosted version](https://xiaoouwang.github.io/LSLDisplayer/).

On load, the **demo example** in `exports/` is fetched automatically. You can then:

- **Select folder** — pick an export directory (uses the File System Access API when available)
- **Choose files** — pick individual CSV/WAV files (multi-select supported; `manifest.json` can be included but is not required)

### Explorer features

- **Synchronized timeline** — align all streams on the LSL session clock (toggle on/off)
- **Marker streams** — keyboard, mouse buttons, PsychoPy markers on a shared timeline
- **Mouse position** — 2D path on the **primary monitor** (1920×1200 in the demo)
- **Audio** — waveform + playback synced to the playhead
- **Events table** — click a row to seek; table scrolls with playback
- **Draggable playhead** — click to seek; drag after a small movement threshold

---

## Exporting data — `demo.py`

Edit the paths at the top of `demo.py`:

```python
xdf_file = "newtest.xdf"
output_dir = Path("exports")
```

Run from the `explorer` folder:

```bash
python demo.py
```

### What it produces

| Output                     | Description                                 |
| -------------------------- | ------------------------------------------- |
| `{index}_{StreamName}.csv` | Marker and position streams                 |
| `{index}_{StreamName}.wav` | Audio streams (16-bit PCM)                  |
| `manifest.json`            | Stream list, LSL timestamps, display layout |

### File naming

Exported files follow: **`{index}_{name}.csv`** or **`.wav`**
Example: `3_PsychoPy.csv`, `5_MyAudioStream.wav`

The explorer expects this naming pattern. **`manifest.json` is optional** when you load a folder or choose files manually (see below).

### CSV formats

**Markers** (single channel):

```csv
timestamp,value
579426.434862231,SPACE pressed
```

**Position** (mouse / 2D), when display metadata is present in the XDF:

```csv
timestamp,monitor,ch_1,ch_2
579422.902208387,Display 1,-1576.0,482.0
579423.0460812482,Primary,1178.0,597.0
```

- `ch_1`, `ch_2` — x/y in **virtual desktop pixels** (one coordinate system across all monitors)
- `monitor` — derived label (`Primary`, `Display 1`, or `Unknown`) from coordinates + layout in `manifest.json`

Monitor layout itself is **not** repeated in every CSV row; it lives in `manifest.json` under the stream's `display` field (from PsychoPy/LSL stream description).

Monitor layout itself is **not** repeated in every CSV row; it lives in `manifest.json` under the stream's `display` field (from PsychoPy/LSL stream description), unless you only have coordinates and an optional `monitor` column in the CSV.

### `manifest.json`

`manifest.json` is produced by `demo.py` alongside the CSV/WAV exports. It is **not required** to open data in the explorer, but it is **strongly recommended** for multimodal sessions.

#### What is required to load data

When using **Select folder** or **Choose files**, the explorer needs at least one file matching:

**`{index}_{StreamName}.csv`** or **`{index}_{StreamName}.wav`**

Examples: `2_Keyboard.csv`, `5_MyAudioStream.wav`

No other file is mandatory. You may load only CSVs, only a WAV, or any subset of export files.

#### What `manifest.json` adds

| Feature | With `manifest.json` | Without `manifest.json` |
| -------- | -------------------- | ------------------------ |
| Loading data | Yes | Yes — numbered CSV/WAV files are enough |
| Stream names & types | From manifest | Inferred from filenames (`3_PsychoPy` → PsychoPy) |
| **Synchronized timeline** | Streams aligned on the shared LSL session clock | Limited — timing is derived per file; cross-stream sync is less reliable |
| **Audio playback** | Aligned to LSL start/end times | WAV plays from local time 0; may not line up with markers or mouse |
| **Mouse monitor frame** | Primary monitor bounds from `display` | No monitor rectangle unless the CSV has a `monitor` column or coordinates alone are used |
| Session stats (start/end) | LSL timestamps from the recording | May show “—” or approximate values |

#### When to include it

- **Optional** — quick inspection of marker CSVs only
- **Recommended** — audio + markers + mouse together, synchronized timeline, or primary-monitor mouse view

#### Built-in demo vs manual loading

The bundled demo in `exports/` always loads `manifest.json` automatically so the example knows which files belong to the session. That is specific to the demo auto-load — it does not mean `manifest.json` is required when you pick your own folder or files.

#### File format

Per-stream fields include index, name, type, channel count, sample rate, start/end LSL time, sample count, and export filename. Position streams may include:

```json
"display": {
  "monitor_count": 2,
  "primary": { "width": 1920, "height": 1200 },
  "virtual_origin": { "width": -2400, "height": 0 },
  "monitors": [
    { "label": "Display 1", "x": -2400, "y": 0, "width": 2400, "height": 1200 },
    { "label": "Primary", "x": 0, "y": 0, "width": 1920, "height": 1200 }
  ]
}
```

The explorer shows only the **Primary** monitor for mouse traces. If the CSV has a `monitor` column, filtering uses that; otherwise coordinates are matched against the layout in the manifest.

---

## Inspecting XDF metadata — `inspect_streams.py`

For users who prefer editing a path in the script rather than using the command line, open `inspect_streams.py` and change:

```python
INPUT_XDF = SCRIPT_DIR / "newtest.xdf"
OUTPUT_HTML = ""  # blank → <recording>_metadata.html in this folder
```

Run:

```bash
python inspect_streams.py
```

By default this writes an **interactive HTML report** (e.g. `newtest_metadata.html`) with stream cards, searchable navigation, and expandable metadata tables.

Optional flags:

| Flag           | Effect                              |
| -------------- | ----------------------------------- |
| `--no-html`    | Skip HTML output                    |
| `--json`       | Print JSON metadata to the terminal |
| `-o path.json` | Save metadata as JSON               |

---

## Loading your own data in the explorer

1. Run `demo.py` on your `.xdf` file (or assemble the same file set manually).
2. In the explorer, use **Select folder** (entire export directory) or **Choose files** (pick one or more numbered CSV/WAV files).
3. Include `manifest.json` in the same folder or selection when you want synchronized timing, audio alignment, and mouse monitor layout.

**Minimum to load:** any `*_*.csv` / `*_*.wav` files matching the export naming pattern.

**Recommended for full visualization:** all export files **plus** `manifest.json` from the same `demo.py` run.

---

## Demo dataset (`exports/`)

The bundled example contains five streams from a PsychoPy session:

| File                  | Stream        | Type                             |
| --------------------- | ------------- | -------------------------------- |
| `1_MousePosition.csv` | MousePosition | Position (with `monitor` column) |
| `2_Keyboard.csv`      | Keyboard      | Markers                          |
| `3_PsychoPy.csv`      | PsychoPy      | Markers                          |
| `4_MouseButtons.csv`  | MouseButtons  | Markers                          |
| `5_MyAudioStream.wav` | MyAudioStream | Audio (48 kHz)                   |

Regenerate after changing `newtest.xdf`:

```bash
python demo.py
```

---

## Credits & partners

- **CoCoLab** — [mshs.univ-cotedazur.fr/plateforme-cocolab](https://mshs.univ-cotedazur.fr/plateforme-cocolab)
- **LSL** — [labstreaminglayer.org](https://labstreaminglayer.org/)
- **PsychoPy** — [psychopy.org](https://psychopy.org/)
- **Huma-Num** — [huma-num.fr](https://www.huma-num.fr/)
- **MSHS Sud-Est** — [mshs.univ-cotedazur.fr](https://mshs.univ-cotedazur.fr/)
