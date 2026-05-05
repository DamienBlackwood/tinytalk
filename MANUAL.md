# CONTROLS

`space`
:   Start recording. Press again to stop and begin transcription.

`esc`
:   Halt at any point. Recording, transcribing, or after results appear, when at the done state, clears the transcript.

`c`
:   Copy transcript to clipboard (only when done).

`a`
:   Toggle autocopy so that every result is copied automatically.

`↑` / `↓`
:   Go through the last 5 transcripts (when done).

`m`
:   Cycle through models forward.

`M`
:   Cycle through models backwards.

`h`
:   Toggle the dev stats panel.

`q`
:   Quit.

# MODELS

There are five models you can cycle through using `m` / `M`. The available models differ by platform.

**macOS (MLX):**

| Label  | Model                     |
|--------|---------------------------|
| TINY   | whisper-tiny              | 
| BASE   | whisper-base              |
| SMALL  | whisper-small             |
| MEDIUM | whisper-medium            |
| TURBO  | whisper-large-v3-turbo    |

Models must be downloaded manually before use:

```bash
hf download mlx-community/whisper-large-v3-turbo
```

Browse all available MLX Whisper models: https://huggingface.co/mlx-community

**Windows / Linux (faster-whisper):**

## update to make sure accurate sizes
| Label  | Model                  | Size |
|--------|------------------------|------|
| TINY   | faster-whisper-tiny    | ~XMB |
| BASE   | faster-whisper-base    | ~XMB |
| SMALL  | faster-whisper-small   | ~XMB |
| MEDIUM | faster-whisper-medium  | ~XGB |
| LARGE  | faster-whisper-large-v3| ~XGB |

Models download automatically on first use for that model. You can also download manually:

```powershell
hf download Systran/faster-whisper-tiny
```

Check all the available faster-whipser models here: https://huggingface.co/Systran

Models are cached at `~/.cache/huggingface/hub/` and only download once.

**Model status icons:**

- `✗` — Not cached. Will download automatically on first use (Windows/Linux) or must be downloaded manually (macOS).
- `↓` — Cached on disk.
- `●` — Locked and loaded.
- `↻` — Downloading now. (Still a work in progress)

# INSTALLATION

**macOS (Apple Silicon):**

```bash
git clone https://github.com/DamienBlackwood/tinytalk.git
cd tinytalk
./install.sh
```

Then run:

```bash
.venv/bin/python tinytalk.py
```

**Windows:**

```powershell
git clone https://github.com/DamienBlackwood/tinytalk.git
cd tinytalk
.\install.ps1
```

Then run:

```powershell
.\.venv\Scripts\python.exe tinytalk.py
```

# FILES

`.tinytalk/config.json`
:   Tinytalk configuration file for the current project directory.

Supported keys:

```json
{
  "model_idx": 0,
  "show_dev": false,
  "auto_copy": false,
  "ascii": false
}
```

Setting `"ascii": true` forces the ASCII fallback renderer

# TERMINALS

tinytalk should work with *any* modern terminal!
