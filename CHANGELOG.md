# Changelog

## v0.4.0

The release to make things stop being finnicky

**Your files stopped living inside the install**

- Config, key and transcripts moved to `~/.tinytalk/` (`%APPDATA%\tinytalk\` on Windows). They used to sit next to the package, which meant a pipx reinstall silently deleted every transcript I had. An old folder gets copied across on first run and left where it is.
- `TINYTALK_HOME` overrides the location if you want per-project logs back.

**First run actually works now**

- Downloading a model no longer asks for `hf auth login`. Every model tinytalk ships is a public repo (I still need to do some test runs on this), so it just downloads. The login hint only shows up if the server actually asks for one.
- A model counts as cached only when its weights are on disk. An interrupted download used to leave a folder with a README in it, which read as "ready" and then failed mid-recording with a stack trace. I had one of these sitting on my own machine the whole time.
- Snapshot lookup takes the newest revision instead of whichever hash sorted first.
- On a fresh install with no config, tinytalk picks the largest model you already have instead of insisting on TURBO.
- The download screen says which model and how big.
- `install.sh` offers to fetch the model the app actually defaults to. It used to download TINY and then start on TURBO.

**It stopped crashing out of curses**

- No microphone, or permission denied, shows a message in the UI instead of a traceback over the terminal.
- macOS hands back a stream of zeros when mic permission is denied rather than erroring, so silent and near-silent clips are caught too. Whisper invents whole sentences out of silence, and now it doesn't get the chance.
- Clips under 0.35s get the same treatment.
- A missing or unreadable `--input` file reports itself in the UI.
- `condition_on_previous_text=False` on both backends, which stops whisper feeding its own output back in and looping on a phrase.

**Reading your transcripts back**

- `tinytalk log`, with `-n`, `--all`, `--today`, `--search`, `--full` and `--export`. They've been encrypted on disk since v0.3 with no way to read them, this is planned to get improved upon even more!

**The dev panel**

- It was anchored to the bottom rail, so its last two lines landed on the keybinds and on the rail itself. It now reserves its own rows and the transcript viewport gives them up.
- It was a rolling deque of half-sentences — `4.2s audio · TURBO`, then `18 words` on the next line, two fragments per run. It's three aligned rows now: model and backend, audio and word count, decode time and realtime ratio.
- While a new run is active, those rows switch to live recording, finishing and transcribing status instead of leaving the previous run's numbers on screen.
- The decode timing is real. `TranscriptionJob` times the call, and the ratio tells you whether the model you picked is keeping up.
- On a short terminal the waveform gives up rows to make room. If even that isn't enough the panel stays hidden and `H` says so instead of quietly doing nothing.
- Opening it no longer flattens the waveform. At 60x24 — which is most people's terminal — the panel took so many rows that the waveform booked one and drew nothing but its own centreline while you talked.
- The `29 words · 8.4s` summary hides while the panel is open, rather than saying it twice.

**Animations**

- The REC chip was `tick % 50 < 35` — a square wave between two colours, which is why it read as a flicker. It's a cosine pulse through four shades of red now, and the processing label does the same through three.
- The typewriter ran at a flat 62 characters a second, so a long transcript took sixteen seconds to appear. It now scales to finish in at most 1.6s regardless of length, with a floor so a two-word answer still gets a moment.
- The transcript cursor keeps its hard blink, because that's what a cursor is, but at a slower cadence.
- The drain is eased, so the bars hang for a beat before dropping away, and it can't run longer than 90 frames.
- The waveform grows peak-hold caps. The `_peak` buffer had been computed every frame since v0.1 and never once drawn.
- The waveform is as tall as the window can spare while you're talking and collapses to a single line once the text arrives, instead of holding a fixed block of rows either way. The transcript gets those rows back — 80x26 with the dev panel open went from two visible lines to four.
- The spinner is a little slower.

**Drawing**

- Everything now goes through one clip pass. Every `addstr` was wrapped in a bare `except`, so anything drawn off the edge just disappeared — a 60-column terminal had been drawing its right rail one column past the edge.
- The waveform gives rows back on short terminals. At the 60x18 minimum the transcript had nowhere to go and simply wasn't drawn.
- The ASCII bar ramp ran backwards, so the quietest bars drew the densest character.
- `┌─ TINYTALK─────` lost its trailing space to the rail fill.
- The footer drops hints from the right instead of overrunning.
- The download bar has a track. The unfilled half was drawn with the space at the front of the block ramp, so a 40% download looked like a bar floating in nothing.
- The typewriter follows its own cursor, so a long transcript no longer types itself out of the viewport.
- Frames are only pushed to the terminal when they change. An idle tinytalk costs nothing.
- `m`/`M` and the settings screen now change the same model. They used to keep separate ideas of which one was selected.

**Housekeeping**

- `--help`, `--version`, `--model`, `--ascii`. `--help` did nothing at all before.
- Unknown flags say so instead of being ignored.
- One version number instead of three, two of which were wrong.
- Clipboard falls back through `wl-copy`, `xclip`, `xsel` on Linux, and says so when it finds none.
- Tests: `python -m unittest discover tests`. They found the clipping and 60x18 bugs above.
- I removed dead code: the unused peak-hold buffer, three identical waveform functions, unused imports and args.
- The lorem ipsum wall in `app.py` is one paragraph repeated instead of forty lines of literal.

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
