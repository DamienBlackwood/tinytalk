# tinytalk

Push-to-talk terminal transcription using local on-device Whisper. macOS uses MLX, Windows and Linux use faster-whisper with automatic GPU acceleration (CUDA) and CPU fallback. No data leaves your device.

Press space to start recording, press again to stop and transcribe.

Full documentation is in `MANUAL.md`.

## How does it look?

<p align="center">
<img src="media/tinytalk-default.gif" alt="kmatrix default">
</p>

## Quick start

Python 3.11+ required.

**macOS (Apple Silicon):**
```bash
git clone https://github.com/DamienBlackwood/tinytalk.git && cd tinytalk
./install.sh
.venv/bin/python tinytalk.py
```

**Windows:**
```powershell
git clone https://github.com/DamienBlackwood/tinytalk.git; cd tinytalk
.\install.ps1
& .\.venv\Scripts\python.exe tinytalk.py
```

On Windows, models download automatically on first use. On macOS, see `MANUAL.md` for model setup. (I'll get to automating it soon, kinda a WIP)

## Rationale

I wanted something quick and keyboard driven to make audio transcription without going through any cloud providers. On Apple Silicon, the Whisper model runs fast enough to perform transcription in "realtime" (after the initial load & compile) without uploading audio anywhere. It uses raw curses the same way my other project, [kmatrix](https://github.com/DamienBlackwood/kmatrix), does.

For now, this was mostly just a means of honing my implementation of curses and because the application is *relatively* simple (compared to my other projects). Stuff like transcriptions showing work well, and the UI is polished enough for my standards, but it doesn't really do anything with the output aside from displaying it, I'll probably add ~~clipboard copying~~ and/or piping it to another command/application soon.

## Under the hood (reflections for me)

It took a few weeks of on-and-off work for the first version, with some genuine problems involved.

One annoying issue was rendering the waveform graphically; it recomputed the entire buffer each time rather than keeping track, leading to graphical glitches with bars moving regardless of audio input. Solved by maintaining a scrolling buffer and adding a single point per update.

Another nasty bug involved Ghostty; for reasons unknown to me, the box-drawing character (like `┌─┐│└┘`) were drawn incorrectly despite font support.

In my case, I use Ghostty, so that meant the `xterm-ghostty` terminfo entry marked them as double-width, which is incorrect. curses uses terminfo to compute new cursor positions, so each `─` character advanced the cursor two columns rather than one. This screwed up all further character drawing.

And the solution was one line: set the `TERM` variable to `xterm-256color` before curses initialization.

## Methodology

All code written and thought out by me, with only **minor** assistance from AI. But mostly drawn from existing research/examples and implemented independently.

## License

MIT