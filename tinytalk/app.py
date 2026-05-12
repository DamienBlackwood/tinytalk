import curses, json, threading, time, collections, subprocess, sys, numpy as np

from pathlib import Path
from . import render
from .audio import AudioCapture, SAMPLE_RATE
from .backend import (
    transcribe, is_model_cached, check_token, download_model,
    MODELS, DEFAULT_MODEL_IDX, BACKEND_NAME,
)
from . import transcripts as transcript_log
from . import crypto as crypto_mod

VERSION  = "v0.2"
FRAME_DT = 1 / 60
TYPE_DT  = 0.016

_model_status: dict[str, str] = {}
_model_status_lock = threading.Lock()
_CFG_PATH = Path(__file__).parent.parent / ".tinytalk" / "config.json"


def _probe_model_status(model_id: str):
    with _model_status_lock:
        _model_status[model_id] = "↓" if is_model_cached(model_id) else "✗"

def _load_cfg():
    try:
        return json.loads(_CFG_PATH.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}

def _save_cfg(data):
    try:
        _CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CFG_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass

def _save_state(app):
    cfg = _load_cfg()
    cfg.update({
        "show_dev":   app.show_dev,
        "model_idx":  app.model_idx,
        "auto_copy":  app.auto_copy,
        "typewriter": app.typewriter,
    })
    _save_cfg(cfg)

N_BARS = 180
PEAK_DECAY = 0.012
NOISE_GATE = 0.003
ATTACK  = 0.55
RELEASE = 0.14
GAIN_ATTACK  = 0.05
GAIN_RELEASE = 0.008


def _build_theme():
    rich = curses.COLORS >= 256
    if rich:
        spec = [
            (1,  237),  # dim
            (2,  248),  # rails
            (3,  255),  # text
            (4,  246),  # label
            (5,  255),  # on (bar core)
            (6,  250),  # mid
            (12, 243),  # soft
            (7,  240),  # glass centerline
            (8,  214),  # proc bright
            (13, 130),  # proc soft
            (9,  211),  # rec
            (10, 79),   # done
            (11, 167),  # err
        ]
    else:
        spec = [
            (1, curses.COLOR_BLACK),  (2, curses.COLOR_WHITE),
            (3, curses.COLOR_WHITE),  (4, curses.COLOR_WHITE),
            (5, curses.COLOR_WHITE),  (6, curses.COLOR_WHITE),
            (12, curses.COLOR_WHITE),
            (7, curses.COLOR_BLACK),
            (8, curses.COLOR_YELLOW), (13, curses.COLOR_YELLOW),
            (9, curses.COLOR_RED),
            (10, curses.COLOR_GREEN), (11, curses.COLOR_RED),
        ]
    for idx, fg in spec:
        try:
            curses.init_pair(idx, fg, -1)
        except curses.error:
            curses.init_pair(idx, fg, curses.COLOR_BLACK)
    return render.Theme(
        dim       = curses.color_pair(1),
        rail      = curses.color_pair(2),
        text      = curses.color_pair(3) | curses.A_BOLD,
        label     = curses.color_pair(4),
        on        = curses.color_pair(5) | curses.A_BOLD,
        mid       = curses.color_pair(6),
        soft      = curses.color_pair(12),
        glass     = curses.color_pair(7),
        proc      = curses.color_pair(8) | curses.A_BOLD,
        proc_soft = curses.color_pair(13),
        rec       = curses.color_pair(9) | curses.A_BOLD,
        done      = curses.color_pair(10) | curses.A_BOLD,
        err       = curses.color_pair(11),
    )


class TranscriptionJob:
    def __init__(self, audio, model_id, mock=False):
        self.audio    = audio
        self.model_id = model_id
        self.mock     = mock

        self.result: str | Exception | None = None
        self.device: str | None = None
        self.download_pct  = -1.0
        self.model_was_cold = False
        self.model_loaded   = False

        self._done   = threading.Event()
        self._cancel = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._cancel.set()

    def is_done(self):
        return self._done.is_set()

    def is_cancelled(self):
        return self._cancel.is_set()

    def _run(self):
        if self._cancel.is_set():
            return

        if self.mock:
            time.sleep(0.3)
            self.result = _MOCK_TEXT
            self.model_loaded = True
            self._done.set()
            return

        t0 = time.perf_counter()

        if not is_model_cached(self.model_id):
            token = check_token()
            if not token:
                self.result = RuntimeError(
                    "model not downloaded  -  run: hf auth login  then try again"
                )
                self._done.set()
                return

            with _model_status_lock:
                _model_status[self.model_id] = "↻"
            self.download_pct = 0.0

            try:
                download_model(self.model_id,
                               progress_cb=lambda pct: setattr(self, "download_pct", pct))
            except Exception as e:
                self.download_pct = -1.0
                self.result = RuntimeError(f"download failed: {e}")
                self._done.set()
                return

            self.download_pct = -1.0
            with _model_status_lock:
                _model_status[self.model_id] = "↓"

        try:
            text, device = transcribe(self.audio, self.model_id, SAMPLE_RATE)
            self.model_loaded = True
            self.result = text
            self.device = device
            with _model_status_lock:
                _model_status[self.model_id] = "●"
        except Exception as e:
            self.result = e

        self._done.set()


class App:
    def __init__(self, scr, mock=False):
        self.scr   = scr
        self._mock = mock
        self.audio = AudioCapture()
        self.state = "idle"
        self.transcript = ""
        self.err = ""
        self.type_pos = 0
        self.type_start = 0.0
        self.spin_i = 0
        self.tick = 0
        cfg = _load_cfg()
        self.model_idx  = cfg.get("model_idx", DEFAULT_MODEL_IDX)
        if not (0 <= self.model_idx < len(MODELS)):
            self.model_idx = DEFAULT_MODEL_IDX
        self._active_model_idx = self.model_idx
        self.show_dev  = cfg.get("show_dev",   False)
        self.auto_copy = cfg.get("auto_copy",  False)
        self.typewriter = cfg.get("typewriter", True)
        self._hist = np.zeros(N_BARS, dtype=np.float32)
        self._peak = np.zeros(N_BARS, dtype=np.float32)
        self._smoothed = 0.0
        self._wave_ceil = render.WAVE_CEIL * 0.24
        self.dev_log = collections.deque(maxlen=6)
        self._job: TranscriptionJob | None = None
        self._captured = None
        self._drain_tick = 0
        self._done_tick  = 0
        self._clipboard_tick = 0
        self._history = collections.deque(
            transcript_log.load_recent(5), maxlen=5
        )
        self._hist_idx = -1
        self._hist_current = ""
        self._append_prefix = ""
        self._listen_start = 0.0
        self._proc_tick = 0
        self._transcribe_device = None
        self._scroll_offset = 0
        self._last_word_count = 0
        self._last_audio_secs = 0.0

        self._in_settings = False
        self._settings_row = 0

        mid = MODELS[self.model_idx][0]
        with _model_status_lock:
            if mid not in _model_status:
                _model_status[mid] = "?"
                threading.Thread(target=_probe_model_status, args=(mid,), daemon=True).start()
        self.theme = None

    def _start_job(self, audio, model_id):
        self._job = TranscriptionJob(audio, model_id, mock=self._mock)
        mid = MODELS[self._active_model_idx][0]
        with _model_status_lock:
            self._job.model_was_cold = _model_status.get(mid) != "●"
        self._job.start()

    def handle_key(self, key):
        if self._in_settings:
            return self._handle_settings_key(key)

        if key in (ord('q'), ord('Q')):
            return False
        if key == 27:
            if self.state == "processing":
                if self._job:
                    self._job.cancel()
                self.state = "idle"; self.scr.clear()
                return True
            if self.state == "done":
                self.transcript = ""; self.err = ""; self.type_pos = 0
                self._hist_idx = -1; self._scroll_offset = 0
                self._append_prefix = ""
                self.state = "idle"; self.scr.clear()
            elif self.state == "listening":
                self.audio.disarm(); self.state = "idle"
                self._hist[:] = 0.0; self._peak[:] = 0.0; self.scr.clear()
            return True
        if key == curses.KEY_RESIZE:
            self._scroll_offset = 0
            self.scr.clear()
        elif key in (ord('s'), ord('S')):
            self._in_settings = True
            self._settings_row = 0
            self.scr.clear()
        elif key in (ord('h'), ord('H')):
            self.show_dev = not self.show_dev
            _save_state(self)
            self.scr.clear()
        elif key in (ord('m'), ord('M')):
            if self.state not in ("listening", "processing", "draining"):
                d = -1 if key == ord('M') else 1
                self._active_model_idx = (self._active_model_idx + d) % len(MODELS)
                self._probe_active_model()
        elif key in (ord('a'), ord('A')):
            if self.state == "done" and self.transcript:
                self._append_prefix = self.transcript
                self._toggle()
        elif key in (ord('c'), ord('C')):
            if self.state == "done" and self.transcript:
                self._do_copy()
        elif key == curses.KEY_UP:
            if self.state == "done":
                self._scroll_offset = max(0, self._scroll_offset - 1)
        elif key == curses.KEY_DOWN:
            if self.state == "done":
                h, w = self.scr.getmaxyx()
                tx_w = min(72, w - 10)
                total = len(render.wrap(self.transcript, tx_w))
                self._scroll_offset = min(self._scroll_offset + 1, max(0, total - 1))
        elif key == ord('['):
            if self.state == "done" and self._history:
                if self._hist_idx == -1:
                    self._hist_current = self.transcript
                next_idx = self._hist_idx + 1
                if next_idx < len(self._history):
                    self._hist_idx = next_idx
                    self.transcript = self._history[self._hist_idx]
                    self.type_pos = len(self.transcript)
                    self._scroll_offset = 0
        elif key == ord(']'):
            if self.state == "done" and self._hist_idx >= 0:
                self._hist_idx -= 1
                self.transcript = self._hist_current if self._hist_idx == -1 else self._history[self._hist_idx]
                self.type_pos = len(self.transcript)
                self._scroll_offset = 0
        elif key == ord(' '):
            if self.state == "processing":
                if self._job:
                    self._job.cancel()
                self.state = "idle"; self.scr.clear()
                return True
            self._toggle()
        return True

    def _handle_settings_key(self, key):
        settings = self._settings_items()
        if key in (27, ord('s'), ord('S'), ord('q'), ord('Q')):
            self._in_settings = False
            self.scr.clear()
        elif key == curses.KEY_UP:
            self._settings_row = max(0, self._settings_row - 1)
        elif key == curses.KEY_DOWN:
            self._settings_row = min(len(settings) - 1, self._settings_row + 1)
        elif key in (ord(' '), ord('\n'), curses.KEY_ENTER, 10, 13):
            self._settings_activate(self._settings_row)
        elif key == curses.KEY_LEFT:
            self._settings_adjust(self._settings_row, -1)
        elif key == curses.KEY_RIGHT:
            self._settings_adjust(self._settings_row, +1)
        return True

    def _settings_items(self):
        return [
            ("Model",       "cycle",  lambda: MODELS[self.model_idx][1],
                            [m[1] for m in MODELS]),
            ("Auto-copy",   "toggle", lambda: self.auto_copy,   None),
            ("Typewriter",  "toggle", lambda: self.typewriter,  None),
            ("Dev panel",   "toggle", lambda: self.show_dev,    None),
        ]

    def _settings_activate(self, row):
        items = self._settings_items()
        if row >= len(items):
            return
        label, kind, getter, options = items[row]
        if kind == "toggle":
            self._settings_set_toggle(label)
        elif kind == "cycle":
            self._settings_adjust(row, +1)

    def _settings_adjust(self, row, delta):
        items = self._settings_items()
        if row >= len(items):
            return
        label, kind, getter, options = items[row]
        if kind == "toggle":
            self._settings_set_toggle(label)
        elif kind == "cycle" and options:
            if label == "Model" and self.state not in ("listening", "processing", "draining"):
                self.model_idx = (self.model_idx + delta) % len(MODELS)
                self._active_model_idx = self.model_idx
                _save_state(self)
                self._probe_current_model()

    def _settings_set_toggle(self, label):
        if label == "Auto-copy":
            self.auto_copy = not self.auto_copy
        elif label == "Typewriter":
            self.typewriter = not self.typewriter
            if not self.typewriter and self.state == "done":
                self.type_pos = len(self.transcript)
        elif label == "Dev panel":
            self.show_dev = not self.show_dev
            self.scr.clear()
        _save_state(self)

    def _probe_current_model(self):
        mid = MODELS[self.model_idx][0]
        with _model_status_lock:
            if _model_status.get(mid) not in ("↓", "●"):
                _model_status[mid] = "?"
                threading.Thread(target=_probe_model_status, args=(mid,), daemon=True).start()

    def _probe_active_model(self):
        mid = MODELS[self._active_model_idx][0]
        with _model_status_lock:
            if _model_status.get(mid) not in ("↓", "●"):
                _model_status[mid] = "?"
                threading.Thread(target=_probe_model_status, args=(mid,), daemon=True).start()

    def _do_copy(self):
        try:
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=self.transcript.encode(), check=False)
            elif sys.platform == "win32":
                subprocess.run(["clip"], input=self.transcript.encode(), check=False)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"],
                               input=self.transcript.encode(), check=False)
            self._clipboard_tick = 45
        except OSError:
            pass

    def _toggle(self):
        if self.state in ("idle", "done"):
            if self.state == "idle":
                self._append_prefix = ""
            self.state = "listening"
            self.transcript = ""; self.err = ""; self.type_pos = 0
            self._hist_idx = -1; self._scroll_offset = 0
            self._peak[:] = 0.0; self._hist[:] = 0.0; self._smoothed = 0.0
            self._wave_ceil = render.WAVE_CEIL * 0.24
            self._listen_start = time.perf_counter()
            self.audio.arm()
        elif self.state == "listening":
            captured = self.audio.disarm()
            if captured is None:
                self.state = "idle"
                return
            self._captured   = captured
            self._drain_tick = 0
            self.state       = "draining"

    def step(self):
        self.tick += 1

        if self.state == "processing" and self._job and self._job.is_cancelled():
            self._job = None
            self.state = "idle"
            self._hist[:] = 0.0; self._peak[:] = 0.0
            return

        if self.state == "processing" and self._job and self._job.is_done():
            job = self._job
            self._job = None
            res = job.result
            if job.device:
                self._transcribe_device = job.device

            if isinstance(res, Exception):
                self.err = str(res); self.transcript = ""
                self.dev_log.append(f"err: {res}")
            else:
                new_text   = (res or "").strip()
                total_secs = len(job.audio) / SAMPLE_RATE
                words      = len(new_text.split()) if new_text else 0
                label      = MODELS[self._active_model_idx][1]
                self._last_word_count = words
                self._last_audio_secs = total_secs
                self.dev_log.append(f"{total_secs:.1f}s audio · {label}")
                self.dev_log.append(f"{words} words")

                if self._append_prefix and new_text:
                    self.transcript = self._append_prefix + " " + new_text
                else:
                    self.transcript = new_text
                self._append_prefix = ""

                if new_text:
                    transcript_log.save(
                        self.transcript, label, total_secs, words
                    )

            self.state      = "done"
            self.type_pos   = 0 if self.typewriter else len(self.transcript)
            self.type_start = time.perf_counter()
            self._done_tick = 0
            self._hist_idx  = -1
            self._scroll_offset = 0
            if self.transcript.strip():
                self._history.appendleft(self.transcript)
            if self.auto_copy and self.transcript:
                self._do_copy()

        if self.state == "done":
            self._done_tick += 1
            if self._clipboard_tick > 0:
                self._clipboard_tick -= 1
            if self.typewriter and self.type_pos < len(self.transcript):
                self.type_pos = min(len(self.transcript),
                                    int((time.perf_counter() - self.type_start) / TYPE_DT))

        if self.state in ("processing", "draining"):
            self.spin_i += 1
        if self.state == "processing":
            self._proc_tick += 1

        if self.state == "draining":
            if self._hist.max() >= 0.001:
                n = len(self._hist)
                t = min(1.0, self._drain_tick / 72.0)
                envelope = np.linspace(1.0 - t * 1.04, 1.0 - t * 0.45, n, dtype=np.float32)
                self._hist *= np.clip(envelope, 0.0, 1.0)
            self._drain_tick += 1
            if self._hist.max() < 0.001:
                self._hist[:] = 0.0
                self.state = "processing"
                self._proc_tick = 0
                mid = MODELS[self._active_model_idx][0]
                self._start_job(self._captured, mid)

        if self.state == "listening":
            raw = self.audio.current_rms()
            gated = max(0.0, raw - NOISE_GATE)
            if gated >= self._smoothed:
                self._smoothed += (gated - self._smoothed) * ATTACK
            else:
                self._smoothed += (gated - self._smoothed) * RELEASE
            p92 = float(np.percentile(self._hist, 92)) if np.any(self._hist) else 0.0
            target_ceil = max(render.WAVE_CEIL * 0.16, p92 * 1.4)
            rate = GAIN_ATTACK if target_ceil >= self._wave_ceil else GAIN_RELEASE
            self._wave_ceil += (target_ceil - self._wave_ceil) * rate
            self._hist[:-1] = self._hist[1:]; self._hist[-1] = self._smoothed
            self._peak[:-1] = self._peak[1:]
            normed_new = min(1.0, (self._smoothed / max(1e-6, self._wave_ceil)) ** 0.65)
            self._peak[-1] = max(self._peak[-1], normed_new)
            self._peak = np.maximum(0.0, self._peak - PEAK_DECAY)

    def draw(self):
        h, w = self.scr.getmaxyx()
        if w < 60 or h < 18:
            self.scr.erase()
            msg = f"resize terminal - need 60x18, got {w}x{h}"
            try:
                self.scr.addstr(max(0, h // 2), max(0, (w - len(msg)) // 2), msg[:max(0, w - 1)])
            except Exception:
                pass
            self.scr.noutrefresh(); curses.doupdate()
            return

        self.scr.erase()

        mid = MODELS[self._active_model_idx][0]
        with _model_status_lock:
            status = _model_status.get(mid, "?")
        model_label = (
            f"{MODELS[self._active_model_idx][1]} "
            f"{status}"
            f"{(' ' + self._transcribe_device) if self._transcribe_device else ''}"
        )

        job = self._job

        if self._in_settings:
            with _model_status_lock:
                status_copy = dict(_model_status)
            crypto_status = (
                f"transcripts encrypted  {render._g()['BULLET']}  {crypto_mod.ENVELOPE_VERSION}"
                if crypto_mod.available()
                else "encryption unavailable  -  pip install cryptography"
            )
            runs = render.compose_settings(
                w, h, self._settings_items(), self._settings_row, self.theme,
                models=MODELS, model_status=status_copy,
                crypto_status=crypto_status,
            )
        else:
            if self.state == "processing" and self._captured is not None:
                live_audio_secs = len(self._captured) / SAMPLE_RATE
            else:
                live_audio_secs = self._last_audio_secs
            live_listen_secs = (
                time.perf_counter() - self._listen_start
                if self.state == "listening" and self._listen_start
                else 0.0
            )
            rs = render.RenderState(
                w=w, h=h,
                state=self.state,
                transcript=self.transcript,
                type_pos=self.type_pos,
                err=self.err,
                tick=self.tick,
                spin_i=self.spin_i,
                hist=self._hist.copy() if self.state in ("listening", "draining") else None,
                show_dev=self.show_dev,
                dev_log=list(self.dev_log),
                version=VERSION,
                model=model_label,
                wave_ceil=self._wave_ceil,
                done_tick=self._done_tick,
                theme=self.theme,
                clipboard_tick=self._clipboard_tick,
                auto_copy=self.auto_copy,
                hist_idx=self._hist_idx,
                hist_len=len(self._history),
                proc_tick=self._proc_tick,
                model_was_cold=job.model_was_cold if job else False,
                model_loaded=job.model_loaded if job else False,
                download_pct=job.download_pct if job else -1.0,
                scroll_offset=self._scroll_offset,
                word_count=self._last_word_count,
                audio_secs=live_audio_secs,
                listen_secs=live_listen_secs,
            )
            runs = render.compose(rs)

        for y, x, text, attr in runs:
            try:
                self.scr.addstr(y, x, text, attr)
            except Exception:
                pass

        try:
            self.scr.move(h - 1, 0)
        except Exception:
            pass
        self.scr.noutrefresh(); curses.doupdate()

    def inject_audio(self, path: str):
        import wave, subprocess as sp
        ext = Path(path).suffix.lower()
        ffmpeg_exts = {".m4a", ".mp3", ".aac", ".ogg", ".flac", ".mp4", ".webm"}

        if ext in ffmpeg_exts:
            try:
                proc = sp.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error",
                     "-i", path, "-f", "f32le", "-ac", "1",
                     "-ar", str(SAMPLE_RATE), "-"],
                    stdout=sp.PIPE, stderr=sp.PIPE, check=True,
                )
            except FileNotFoundError:
                raise RuntimeError("ffmpeg not found, install it to load M4A/MP3 files")
            audio = np.frombuffer(proc.stdout, dtype=np.float32)
        else:
            try:
                import soundfile as sf
                audio, sr = sf.read(path, dtype="float32", always_2d=False)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                if sr != SAMPLE_RATE:
                    import math
                    from scipy.signal import resample_poly
                    g = math.gcd(SAMPLE_RATE, sr)
                    audio = resample_poly(audio, SAMPLE_RATE // g, sr // g).astype(np.float32)
            except ImportError:
                with wave.open(path, "rb") as wf:
                    sr = wf.getframerate()
                    raw = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    if wf.getnchannels() == 2:
                        audio = audio.reshape(-1, 2).mean(axis=1)
                    if sr != SAMPLE_RATE:
                        new_len = int(len(audio) * SAMPLE_RATE / sr)
                        audio = np.interp(np.linspace(0, len(audio) - 1, new_len),
                                          np.arange(len(audio)), audio).astype(np.float32)

        self._captured = audio
        self.state = "processing"
        self._proc_tick = 0
        mid = MODELS[self._active_model_idx][0]
        self._start_job(audio, mid)

    def run(self, input_path: str | None = None):
        curses.curs_set(0); self.scr.nodelay(1); self.scr.keypad(1)
        if not curses.has_colors():
            raise SystemExit("tinytalk requires a colour terminal")
        curses.start_color(); curses.use_default_colors()
        self.theme = _build_theme()
        if input_path:
            self.inject_audio(input_path)
        try:
            while True:
                while True:
                    key = self.scr.getch()
                    if key == -1:
                        break
                    if not self.handle_key(key):
                        return
                self.step(); self.draw()
                static = (self.state == "done"
                          and not (self.typewriter and self.type_pos < len(self.transcript))
                          and self._clipboard_tick == 0)
                if static and not self._in_settings:
                    time.sleep(1 / 10)
                elif self.state in ("idle", "done") and not self._in_settings:
                    time.sleep(1 / 20)
                else:
                    time.sleep(FRAME_DT)
        finally:
            self.audio.stop()


_MOCK_TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Duis finibus enim a sagittis fringilla. "
    "Aliquam erat volutpat. Morbi quis nulla condimentum, auctor diam in, ultricies magna. Curabitur sit "
    "amet condimentum dolor. Mauris efficitur nulla magna, et venenatis libero eleifend eget. Praesent in "
    "dapibus lacus, quis pellentesque urna. Vestibulum ante ipsum primis in faucibus orci luctus et ultrices "
    "posuere cubilia curae; Morbi sagittis, turpis et tincidunt malesuada, nisl elit efficitur enim, sed "
    "venenatis eros eros iaculis mi. Mauris vehicula consectetur hendrerit. Nulla quis dolor et turpis "
    "consequat volutpat. Phasellus tortor odio, eleifend vitae velit sed, tempor mattis risus. "
    "Vivamus vitae odio arcu. Proin malesuada odio rhoncus, congue urna eu, pulvinar dolor. Nam id orci quam. "
    "Mauris rhoncus dui sapien, eget elementum leo semper tempor. Pellentesque ullamcorper est libero, at "
    "scelerisque tortor pulvinar quis. Proin interdum ac nibh sit amet elementum. Ut ac purus id tortor "
    "suscipit facilisis. Curabitur ipsum metus, rutrum ut feugiat eu, ullamcorper quis metus. Mauris in augue "
    "magna. Quisque quis volutpat enim. Sed quis leo eget dui pulvinar maximus eu a sapien. In dignissim "
    "commodo turpis non viverra. In quam massa, pulvinar at maximus sit amet, blandit nec metus. Vestibulum "
    "gravida nisl malesuada, finibus odio id, tempus dolor. Praesent dictum imperdiet lacus eu viverra. "
    "Aenean egestas, massa at egestas commodo, sem nulla lacinia arcu, vel accumsan nunc odio a dolor. Donec "
    "ac hendrerit arcu. Maecenas vel nunc laoreet, feugiat elit vitae, posuere felis. Morbi porttitor rutrum "
    "efficitur. Duis lobortis auctor augue, quis dignissim metus aliquet quis. Proin egestas ligula arcu, sit "
    "amet aliquet ante rhoncus in. Donec in enim nec augue volutpat vehicula. Aenean velit arcu, auctor a "
    "porta ac, cursus at orci. Proin convallis arcu neque, iaculis efficitur leo interdum eget. Maecenas "
    "venenatis sapien eros, ac pellentesque enim auctor et. Donec scelerisque vestibulum semper. Sed posuere "
    "scelerisque nulla et blandit. Duis erat lorem, congue nec sem quis, porttitor iaculis metus. Nullam non "
    "ipsum at est fringilla faucibus. Donec id sem ligula. Morbi risus mauris, pharetra id mi sed, efficitur "
    "placerat lacus. Proin elementum enim at quam efficitur, sed dapibus erat ultrices. Mauris suscipit ligula "
    "in diam lobortis, in iaculis dui condimentum. Phasellus fringilla orci eu congue commodo. Nullam sagittis "
    "dignissim faucibus. Donec a maximus turpis. Maecenas diam risus, interdum nec nunc ac, maximus malesuada "
    "dui. Suspendisse faucibus maximus ante nec vehicula. Vivamus ultricies accumsan mauris, ac imperdiet magna "
    "lobortis vitae. Phasellus eleifend diam mauris, vitae mollis mauris dapibus et. Fusce consectetur massa "
    "mi, eu tincidunt ligula sodales consectetur. Nulla metus turpis, elementum posuere arcu ac, maximus "
    "placerat purus. Quisque id lorem euismod, imperdiet nisi ut, finibus tortor. Cras auctor tristique "
    "feugiat. Curabitur ac mattis felis. Fusce porta ipsum risus, quis condimentum mi bibendum sit amet. "
    "Donec condimentum leo diam, in scelerisque neque porta sit amet. Nunc hendrerit id dui vitae fringilla. "
    "Etiam tristique interdum metus non vulputate. Nulla viverra sed ex in congue. Nunc in molestie nibh. "
    "Suspendisse cursus ligula sapien. Nunc metus sem."
)

def main():
    import locale, os, argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--input", metavar="FILE", default=None)
    p.add_argument("--mock", action="store_true")
    args, _ = p.parse_known_args()

    if sys.platform == "win32":
        os.system("chcp 65001 >nul 2>&1")
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    if os.environ.get("TERM") == "xterm-ghostty":
        os.environ["TERM"] = "xterm-256color"

    cfg = _load_cfg()
    if "ascii" in cfg:
        render.USE_ASCII = bool(cfg["ascii"])
    else:
        if sys.platform == "win32":
            import io
            stdout_enc = getattr(sys.stdout, "encoding", "") or ""
            render.USE_ASCII = "utf" not in stdout_enc.lower()
        else:
            enc = locale.getpreferredencoding(False)
            try:
                "┌│└".encode(enc)
                render.USE_ASCII = False
            except (UnicodeEncodeError, LookupError):
                render.USE_ASCII = True

    input_path = args.input
    if input_path and not Path(input_path).is_absolute():
        input_path = str(Path("audio-input") / input_path)

    try:
        curses.wrapper(lambda scr: App(scr, mock=args.mock).run(input_path))
    except KeyboardInterrupt:
        pass
