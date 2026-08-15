# CONTROLS

`space`
:   Start recording. Press again to stop and begin transcription.

`esc`
:   Halt at any point. Recording, transcribing, or after results appear, when at the done state, clears the transcript.

`a`
:   Record again and append to the transcript you already have.

`c`
:   Copy transcript to clipboard (only when done).

`↑` / `↓`
:   Scroll through transcript (when done).

`[` / `]`
:   Navigate backward/forward through the last 5 transcripts (when done).

`m` / `M`
:   Cycle through models forward/backward.

`s`
:   Open settings (model, auto-copy, typewriter, dev panel).

`h`
:   Toggle the dev stats panel — model and backend, audio length and word count,
    decode time and realtime ratio. It takes rows from the waveform, and hides
    itself on a window too short to hold it.

`q`
:   Quit.

# COMMAND LINE

```
tinytalk                    start the recorder
tinytalk --input FILE       transcribe an audio file instead of recording
tinytalk --model turbo      use a specific model for this run only
tinytalk --ascii            force the ASCII renderer
tinytalk --mock             fake transcription, for poking at the UI
tinytalk --version
tinytalk --help
```

`--input` takes anything ffmpeg can read. Without ffmpeg installed it falls back to plain 16-bit WAV. A bare filename is also looked up in `audio-input/`.

# READING TRANSCRIPTS BACK

```
tinytalk log                  | the last 20
tinytalk log -n 50            | the last 50
tinytalk log --all            | everything
tinytalk log --today          | only today's
tinytalk log --search dog     | only ones mentioning "dog"
tinytalk log --full           | whole transcripts
tinytalk log --export out.txt | plaintext (--force to overwrite)
```

# MODELS

**macOS (MLX):**

| Label  | Model                  | Size    |
|--------|------------------------|---------|
| TINY   | whisper-tiny           | ~75MB   |
| BASE   | whisper-base-mlx       | ~145MB  |
| MEDIUM | whisper-medium-mlx     | ~1.5GB  |
| TURBO  | whisper-large-v3-turbo | ~1.6GB  |

Check all available MLX Whisper models: https://huggingface.co/mlx-community

**Windows and Linux (faster-whisper):**

| Label  | Model                   | Size   |
|--------|-------------------------|--------|
| TINY   | faster-whisper-tiny     | ~75MB  |
| BASE   | faster-whisper-base     | ~145MB |
| SMALL  | faster-whisper-small    | ~484MB |
| MEDIUM | faster-whisper-medium   | ~1.5GB |
| LARGE  | faster-whisper-large-v3 | ~3GB   |

Check all available faster-whisper models: https://huggingface.co/Systran

Models download automatically on first use these repos are public, so no account is needed. To pre-download one yourself:

```bash
hf download mlx-community/whisper-large-v3-turbo
```

Models are cached at `~/.cache/huggingface/hub/` and only download once. If you set
`HF_HOME` or `HF_HUB_CACHE`, tinytalk looks there instead.

**Model status icons:**

- `✗` — Not cached. Downloads automatically on first use.
- `↓` — Cached on disk.
- `●` — Locked and loaded.
- `↻` — Downloading now.

A model only counts as cached once its weights are actually on disk, so an interrupted download shows as `✗` rather than failing halfway through a recording.

# INSTALLATION

**macOS (Apple Silicon):**

```bash
git clone https://github.com/DamienBlackwood/tinytalk.git
cd tinytalk
./install.sh
```

Then run `tinytalk` from anywhere.

**Windows:**

```powershell
git clone https://github.com/DamienBlackwood/tinytalk.git
cd tinytalk
.\install.ps1
```

Then run:

```powershell
.\.venv\Scripts\tinytalk.exe
```

**Anywhere else (Linux):**

```bash
pipx install .
```

Clipboard support on Linux uses `wl-copy`, `xclip` or `xsel`, whichever it finds first.

# FILES

Everything lives in `~/.tinytalk/` (`%APPDATA%\tinytalk\` on Windows). Set
`TINYTALK_HOME` to put it somewhere else — handy if you want per-project logs.

`config.json`
:   Settings, written whenever you change one.

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

`transcripts.jsonl`
:   One line per transcription. The text is encrypted, the metadata (timestamp, model, duration, word count) is not.

`key`
:   The AES-256 key for the above, mode `0600`. Delete it and every existing transcript becomes unreadable.

Earlier versions kept all three next to the package, which meant a pipx reinstall
threw them away. tinytalk copies an old folder across the first time it runs and
leaves the original alone.

# TERMINALS

tinytalk should work with *any* modern terminal! It needs 60x18 at minimum, and
gives the waveform more room as the window gets taller.
