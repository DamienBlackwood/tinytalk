# tinytalk

Push-to-talk terminal transcription application using local-on-device Whisper through MLX.

Press space to start recording. Release to trigger transcription. No data leaves your device.

Full documentation is found within `MANUAL.md`.

## Quick start

Python 3.11+ and Apple Silicon required.

```bash
git clone https://github.com/DamienBlackwood/tinytalk.git
cd tinytalk
pipx install .
```

Now run `tinytalk` from any folder!

## Rationale

Needed something quick and keyboard driven to push audio transcription into applications without going through any cloud APIs. On the Apple Silicon platform, the Whisper model runs fast enough to perform transcription in "realtime" without uploading audio anywhere (after the first load). Uses raw curses same way my other project, [kmatrix](https://github.com/DamienBlackwood/kmatrix), does.

For now, this was mostly just a means of honing my implementation of curses and because the application is relatively simple, transcription works well, UI is pretty nice, but it doesn't really do anything with the output, aside from displaying it, I'll probably add clipboard copying or piping it to another command/application

## Under the hood

It took a few weeks of on-and-off work for the first version, with some genuine stupidity involved.

One annoying issue was rendering the waveform graphically; it recomputed the entire buffer each time rather than keeping track, leading to graphical glitches with bars moving regardless of audio input. Solved by maintaining a scrolling buffer and adding a single point per update.

Another nasty bug involved Ghostty; for reasons unknown to me, the box-drawing character (like `┌─┐│└┘`) were drawn incorrectly despite font support.

In my case, I use Ghostty, so that meant the `xterm-ghostty` terminfo entry marked them as double-width, which is incorrect. curses uses terminfo to compute new cursor positions, so each `-` character advanced the cursor two columns rather than one. This screwed up all further character drawing.

And the solution was one line: set the `TERM` variable to `xterm-256color` before curses initialization.

## Methodology

All code written by me, drawing from existing research but implemented independently. No AI was used.

## License

MIT