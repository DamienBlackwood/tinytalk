import curses, json, threading, time, collections, subprocess, numpy as np
from pathlib import Path
from . import render
from .audio import AudioCapture, SAMPLE_RATE
from .whisper import transcribe, _HF_CACHE

VERSION  = "v0.2"
FRAME_DT = 1 / 60
TYPE_DT  = 0.016

MODELS = [
    ("mlx-community/whisper-tiny",           "TINY"),
    ("mlx-community/whisper-base",           "BASE"),
    ("mlx-community/whisper-small",          "SMALL"),
    ("mlx-community/whisper-medium",         "MEDIUM"),
    ("mlx-community/whisper-large-v3-turbo", "TURBO"),
]
DEFAULT_MODEL_IDX = 4  # set this to whatever you'd like!

_model_status: dict[str, str] = {}
_CFG_PATH = Path(__file__).parent.parent / ".tinytalk" / "config.json"


def _check_model_cached(model_id: str) -> str:
    folder    = _HF_CACHE / ("models--" + model_id.replace("/", "--"))
    snapshots = folder / "snapshots"
    if snapshots.exists() and any(snapshots.iterdir()):
        return "↓"
    return "✗"


def _probe_model_status(model_id: str):
    _model_status[model_id] = _check_model_cached(model_id)

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
    _save_cfg({"show_dev": app.show_dev, "model_idx": app.model_idx, "auto_copy": app.auto_copy})

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
    t = render.Theme()
    t.dim = curses.color_pair(1)
    t.rail = curses.color_pair(2)
    t.text = curses.color_pair(3) | curses.A_BOLD
    t.label = curses.color_pair(4)
    t.on = curses.color_pair(5) | curses.A_BOLD
    t.mid = curses.color_pair(6)
    t.soft = curses.color_pair(12)
    t.glass = curses.color_pair(7)
    t.proc = curses.color_pair(8) | curses.A_BOLD
    t.proc_soft = curses.color_pair(13)
    t.rec = curses.color_pair(9) | curses.A_BOLD
    t.done = curses.color_pair(10) | curses.A_BOLD
    t.err = curses.color_pair(11)
    return t


class App:
    def __init__(self, scr):
        self.scr   = scr
        self.audio = AudioCapture()
        self.state = "idle"
        self.transcript = ""
        self.err = ""
        self.type_pos = 0
        self.type_start = 0.0
        self.spin_i = 0
        self.tick = 0
        cfg = _load_cfg()
        self.model_idx = cfg.get("model_idx", DEFAULT_MODEL_IDX)
        if not (0 <= self.model_idx < len(MODELS)):
            self.model_idx = DEFAULT_MODEL_IDX
        self.show_dev = cfg.get("show_dev", False)
        self.auto_copy = cfg.get("auto_copy", False)
        self._hist = np.zeros(N_BARS, dtype=np.float32)
        self._peak = np.zeros(N_BARS, dtype=np.float32)
        self._smoothed = 0.0
        self._wave_ceil = render.WAVE_CEIL * 0.24
        self.dev_log = collections.deque(maxlen=6)
        self._result_evt = threading.Event()
        self._cancel_evt = threading.Event()
        self._result = None
        self._captured = None
        self._drain_tick = 0
        self._done_tick  = 0
        self._clipboard_tick = 0
        self._history = collections.deque(maxlen=5)
        self._hist_idx = -1
        self._hist_current = ""
        self._proc_tick = 0
        self._model_was_cold = False

        mid = MODELS[self.model_idx][0]
        if mid not in _model_status:
            _model_status[mid] = "?"
            threading.Thread(target=_probe_model_status, args=(mid,), daemon=True).start()
        self.theme = None

    def handle_key(self, key):
        if key in (ord('q'), ord('Q')):
            return False
        if key == 27:
            if self.state == "processing":
                self._cancel_evt.set(); self.state = "idle"; self.scr.clear()
                return True
            if self.state == "done":
                self.transcript = ""; self.err = ""; self.type_pos = 0
                self._hist_idx = -1
                self.state = "idle"; self.scr.clear()
            elif self.state == "listening":
                self.audio.disarm(); self.state = "idle"
                self._hist[:] = 0.0; self._peak[:] = 0.0; self.scr.clear()
            return True
        if key == curses.KEY_RESIZE:
            self.scr.clear()
        elif key in (ord('h'), ord('H')):
            self.show_dev = not self.show_dev
            _save_state(self)
            self.scr.clear()
        elif key == ord('m'):
            if self.state in ("idle", "done"):
                self.model_idx = (self.model_idx + 1) % len(MODELS)
                _save_state(self)
                self._probe_current_model()
        elif key == ord('M'):
            if self.state in ("idle", "done"):
                self.model_idx = (self.model_idx - 1) % len(MODELS)
                _save_state(self)
                self._probe_current_model()
        elif key in (ord('c'), ord('C')):
            if self.state == "done" and self.transcript:
                self._do_copy()
        elif key in (ord('a'), ord('A')):
            if self.state in ("idle", "done"):
                self.auto_copy = not self.auto_copy
                _save_state(self)
        elif key == curses.KEY_UP:
            if self.state == "done" and self._history:
                if self._hist_idx == -1:
                    self._hist_current = self.transcript
                next_idx = self._hist_idx + 1
                if next_idx < len(self._history):
                    self._hist_idx = next_idx
                    self.transcript = self._history[self._hist_idx]
                    self.type_pos = len(self.transcript)
        elif key == curses.KEY_DOWN:
            if self.state == "done" and self._hist_idx >= 0:
                self._hist_idx -= 1
                self.transcript = self._hist_current if self._hist_idx == -1 else self._history[self._hist_idx]
                self.type_pos = len(self.transcript)
        elif key == ord(' '):
            if self.state == "processing":
                self._cancel_evt.set(); self.state = "idle"; self.scr.clear()
                return True
            self._toggle()
        return True

    def _probe_current_model(self):
        mid = MODELS[self.model_idx][0]
        if _model_status.get(mid) not in ("↓", "●"):
            _model_status[mid] = "?"
            threading.Thread(target=_probe_model_status, args=(mid,), daemon=True).start()

    def _do_copy(self):
        try:
            subprocess.run(["pbcopy"], input=self.transcript.encode(), check=False)
            self._clipboard_tick = 45
        except OSError:
            pass

    def _toggle(self):
        if self.state in ("idle", "done"):
            self.state = "listening"
            self.transcript = ""; self.err = ""; self.type_pos = 0
            self._hist_idx = -1
            self._peak[:] = 0.0; self._hist[:] = 0.0; self._smoothed = 0.0
            self._wave_ceil = render.WAVE_CEIL * 0.24
            self.audio.arm()
        elif self.state == "listening":
            self._captured    = self.audio.disarm()
            self._drain_tick  = 0
            self.state        = "draining"

    def _do_transcribe(self, audio, model_id):
        if self._cancel_evt.is_set():
            self._cancel_evt.clear(); return
        t0 = time.perf_counter()
        try:
            text = transcribe(audio, model_id, SAMPLE_RATE)
            self._result = text
            _model_status[model_id] = "●"
            secs    = len(audio) / SAMPLE_RATE
            elapsed = time.perf_counter() - t0
            words   = len(text.split()) if text.strip() else 0
            ratio   = secs / elapsed if elapsed > 0 else 0
            label   = MODELS[self.model_idx][1]
            self.dev_log.append(f"{secs:.1f}s → {elapsed:.1f}s  ({ratio:.1f}× realtime)")
            self.dev_log.append(f"{words} words  ·  {label}")
        except Exception as e:
            self._result = e
            self.dev_log.append(f"err: {e}")
        self._result_evt.set()

    def step(self):
        self.tick += 1

        if self.state == "processing" and self._cancel_evt.is_set():
            self._cancel_evt.clear(); self.state = "idle"
            self._hist[:] = 0.0; self._peak[:] = 0.0
            return

        if self.state == "processing" and self._result_evt.is_set():
            res = self._result
            if isinstance(res, Exception):
                self.err = str(res); self.transcript = ""
            else:
                self.transcript = res or ""
            self.state       = "done"
            self.type_pos    = 0
            self.type_start  = time.perf_counter()
            self._done_tick  = 0
            self._hist_idx   = -1
            if self.transcript.strip():
                self._history.appendleft(self.transcript)
            if self.auto_copy and self.transcript:
                self._do_copy()

        if self.state == "done":
            self._done_tick += 1
            if self._clipboard_tick > 0:
                self._clipboard_tick -= 1
            if self.type_pos < len(self.transcript):
                self.type_pos = min(len(self.transcript), int((time.perf_counter() - self.type_start) / TYPE_DT))

        if self.state in ("processing", "draining"):
            self.spin_i += 1
        if self.state == "processing":
            self._proc_tick += 1

        if self.state == "draining":
            if self._hist.max() >= 0.001:
                n = len(self._hist)
                t = min(1.0, self._drain_tick / 72.0)
                envelope = np.linspace(1.0 - t * 0.96, 1.0 - t * 0.30, n, dtype=np.float32)
                self._hist *= np.clip(envelope, 0.0, 1.0)
            self._drain_tick += 1
            if self._hist.max() < 0.001:
                self._hist[:] = 0.0
                self.state = "processing"
                self._result_evt.clear()
                self._result = None
                self._proc_tick = 0
                mid = MODELS[self.model_idx][0]
                self._model_was_cold = _model_status.get(mid) != "●"
                threading.Thread(
                    target=self._do_transcribe,
                    args=(self._captured, mid),
                    daemon=True,
                ).start()

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
            except:
                pass
            self.scr.noutrefresh(); curses.doupdate()
            return

        self.scr.erase()

        for y, x, text, attr in render.compose(
            w, h, self.state, self.transcript, self.type_pos, self.err,
            self.tick, self.spin_i,
            self._hist.copy() if self.state in ("listening", "draining") else None,
            self.show_dev, list(self.dev_log), VERSION,
            f"{MODELS[self.model_idx][1]} {_model_status.get(MODELS[self.model_idx][0], '?')}",
            self._wave_ceil, self._done_tick,
            self.theme,
            self._clipboard_tick, self.auto_copy,
            self._hist_idx, len(self._history),
            self._proc_tick, self._model_was_cold,
        ):
            try:
                self.scr.addstr(y, x, text, attr)
            except:
                pass

        try:
            self.scr.move(h - 1, 0)
        except:
            pass
        self.scr.noutrefresh(); curses.doupdate()

    def run(self):
        curses.curs_set(0); self.scr.nodelay(1); self.scr.keypad(1)
        if not curses.has_colors():
            raise SystemExit("tinytalk requires a colour terminal")
        curses.start_color(); curses.use_default_colors()
        self.theme = _build_theme()
        try:
            while True:
                key = self.scr.getch()
                if not self.handle_key(key):
                    break
                self.step(); self.draw()
                time.sleep(FRAME_DT)
        finally:
            self.audio.stop()


def main():
    import locale, os
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
        enc = locale.getpreferredencoding(False)
        try:
            "┌│└".encode(enc)
            render.USE_ASCII = False
        except (UnicodeEncodeError, LookupError):
            render.USE_ASCII = True

    try:
        curses.wrapper(lambda scr: App(scr).run())
    except KeyboardInterrupt:
        pass
