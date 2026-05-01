# Changelog

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
