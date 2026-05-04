# Changelog

## v0.2.0

- Clipboard: `c` copies transcript. `a` toggles autocopy (both are persistent)
- History: `↑` / `↓` in done state steps through last 5 transcripts.
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
