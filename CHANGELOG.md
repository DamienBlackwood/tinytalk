# Changelog

## v0.3.0

- Encrypted transcripts: every transcription is logged to `.tinytalk/transcripts.jsonl` and the text is encrypted with AES-256-GCM. Key sits at `.tinytalk/key`. Metadata (timestamp, model, duration, word count) stays in the clear.
- Unified backend: `whisper.py` became `backend.py` — one module hides the MLX vs faster-whisper split, including the model list and platform check.
- Faster-whisper LRU: switching models no longer keeps every loaded model resident in memory.
- Faster-whisper stdout/stderr is now suppressed so first-load chatter doesn't smear the curses UI.
- ESC latency: `set_escdelay(25)` knocks ~975ms off the lag between pressing ESC and the UI clearing.
- Processing screen now reads "2.3 seconds long" instead of "2.3s" while transcribing.
- Refactor: `App.draw` takes a `RenderState` dataclass instead of 23 positional args.
- Refactor: the transcription thread, cancel/done events, and progress state are pulled into a `TranscriptionJob` class.
- Refactor: settings are a `Setting` dataclass with per-row `apply(delta)` instead of three label-dispatch methods.
- Fixed: toggling any UI setting no longer wipes the manually-set `ascii` key in `config.json`.
- Fixed: docs (`MANUAL.md`, `CHANGELOG.md`) now match the keybindings the code actually has.
- Fixed: `pyproject.toml` declares the runtime deps the app needs (`huggingface_hub[cli]`, `tqdm`, `mlx-whisper`, `faster-whisper`, `windows-curses`, `cryptography`).
- Fixed: dead `_drain_tick = 999` removed from `inject_audio`.
- `Theme` is a `@dataclass` instead of a bag-of-attributes.

## v0.2.0

- Clipboard: `c` copies transcript. Auto-copy toggle lives in settings (`s`).
- History: `[` / `]` in done state steps through last 5 transcripts.
- Scroll: `↑` / `↓` scrolls long transcripts in done state.
- Dev log now shows timing, realtime ratio, word count, and model used per transcription.
- Cold model load shows "loading model" instead of "transcribing" on first use (I plan to make it more robust later).
- Fixed: bare `except` in `_save_cfg` narrowed to `OSError`.
- Fixed: long sentences in transcript now wrap properly instead of truncating.
- Mic stream closes immediately after recording stops.

## v0.1.0

Initial release.

- Push-to-talk recording via `space`. Live RMS waveform while listening.
- On-device transcription via MLX Whisper. No network calls after model download.
- Five models: TINY → TURBO. Switch with `m` / `M` while idle. Selection persists.
- Model status indicators: `✗` not installed, `↓` cached, `●` hot in memory.
- Drain animation: bars collapse after recording stops, before transcription begins.
- Transcript fades in with a typewriter effect.
- Dev overlay (`h`) shows per-transcription timing.
- Config saved to `.tinytalk/config.json` in the project directory.
- ASCII fallback for terminals without box-drawing font coverage.
- Ghostty: auto-patches `TERM` to fix terminfo char-width bug with `xterm-ghostty`.
