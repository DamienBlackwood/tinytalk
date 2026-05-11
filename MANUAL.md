# CONTROLS

`space`
:   Start recording. Press again to stop and begin transcription.

`esc`
:   Halt at any point. Recording, transcribing, or after results appear, when at the done state, clears the transcript.

`c`
:   Copy transcript to clipboard (only when done).

`↑` / `↓`
:   Scroll through transcript (when done).

`]` / `[`
:   Navigate forward/backward through the last 5 transcripts (when done).

`m` / `M`
:   Cycle through models forward/backward.

`s`
:   Open settings (auto-copy, typewriter, dev panel, model).

`h`
:   Toggle the dev stats panel.

`q`
:   Quit.

# MODELS

**macOS (MLX):**

| Label  | Model                  | Size    |
|--------|------------------------|---------|
| TINY   | whisper-tiny           | ~71MB   |
| BASE   | whisper-base-mlx       | ~137MB  |
| MEDIUM | whisper-medium-mlx     | ~1.5GB  |
| TURBO  | whisper-large-v3-turbo | ~1.5GB  |

Models download automatically on first use. To pre-download manually:

```bash
hf download mlx-community/whisper-large-v3-turbo
```

Check all available MLX Whisper models: https://huggingface.co/mlx-community

**Windows (faster-whisper):**

| Label  | Model                   | Size   |
|--------|-------------------------|--------|
| TINY   | faster-whisper-tiny     | ~75MB  |
| BASE   | faster-whisper-base     | ~141MB |
| SMALL  | faster-whisper-small    | ~464MB |
| MEDIUM | faster-whisper-medium   | ~1.5GB |
| LARGE  | faster-whisper-large-v3 | ~3GB   |

Models download automatically on first use. To pre-download manually:

```powershell
hf download Systran/faster-whisper-tiny
```

Check all available faster-whisper models: https://huggingface.co/Systran

Models are cached at `~/.cache/huggingface/hub/` and only download once.

**Model status icons:**

- `✗` — Not cached. Will download automatically on first use (requires `hf auth login`).
- `↓` — Cached on disk.
- `●` — Locked and loaded.
- `↻` — Downloading now.

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
  "typewriter": true,
  "ascii": false
}
```

Setting `"ascii": true` forces the ASCII fallback renderer. Setting `"typewriter": false` disables the character-by-character animation when showing transcripts.

# TERMINALS

tinytalk should work with *any* modern terminal!
