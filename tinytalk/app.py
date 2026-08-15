import collections
import curses
import json
import subprocess
import sys
import threading
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import __version__
from . import crypto as crypto_mod
from . import paths, render
from . import transcripts as transcript_log
from .audio import AudioCapture, MicError, SAMPLE_RATE, check_clip, load_file
from .backend import (
    BACKEND_NAME, MODELS, default_model_idx, download_model, is_model_cached,
    size_label, transcribe,
)


@dataclass
class Setting:
    label: str
    kind: str
    getter: Callable[[], Any]
    apply: Callable[[int], None]
    options: list[str] | None = None


VERSION  = "v" + ".".join(__version__.split(".")[:2])
FRAME_DT = 1 / 60
IDLE_DT  = 1 / 30
TYPE_DT  = 0.016     # per character, until it takes take all day
TYPE_MIN = 0.35      # a two word transcript still gets a moment
TYPE_MAX = 1.6       # and a thousand word one doesn't take a trillion years

_model_status: dict[str, str] = {}
_model_status_lock = threading.Lock()


def _set_status(repo: str, status: str):
    with _model_status_lock:
        _model_status[repo] = status


def _get_status(repo: str) -> str:
    with _model_status_lock:
        return _model_status.get(repo, render.UNKNOWN)


def _probe(repo: str):
    _set_status(repo, render.CACHED if is_model_cached(repo) else render.MISSING)


def _probe_async(repo: str):
    """Hitting the disk to look for a 1.6GB model shouldn't stall a frame."""
    with _model_status_lock:
        if _model_status.get(repo) in (render.CACHED, render.HOT, render.BUSY):
            return
        _model_status[repo] = render.UNKNOWN
    threading.Thread(target=_probe, args=(repo,), daemon=True).start()


def _load_cfg():
    try:
        data = json.loads(paths.CONFIG.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save_cfg(data):
    try:
        if not paths.ensure_home():
            return
        paths.CONFIG.write_text(json.dumps(data, indent=2))
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
PEAK_DECAY = 0.008   # how fast a peak cap sinks back down, as a share of the ceiling
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
            (17, 172),  # proc mid
            (13, 130),  # proc soft
            (9,  211),  # rec bright
            (16, 175),  # rec mid
            (15, 132),  # rec soft
            (14, 95),   # rec dim
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
            (8, curses.COLOR_YELLOW), (17, curses.COLOR_YELLOW),
            (13, curses.COLOR_YELLOW),
            (9, curses.COLOR_RED),  (16, curses.COLOR_RED),
            (15, curses.COLOR_RED), (14, curses.COLOR_RED),
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
        proc_mid  = curses.color_pair(17),
        proc_soft = curses.color_pair(13),
        rec       = curses.color_pair(9) | curses.A_BOLD,
        rec_mid   = curses.color_pair(16),
        rec_soft  = curses.color_pair(15),
        rec_dim   = curses.color_pair(14),
        done      = curses.color_pair(10) | curses.A_BOLD,
        err       = curses.color_pair(11),
    )


def _copy_to_clipboard(text: str) -> bool:
    if sys.platform == "darwin":
        tools = [["pbcopy"]]
    elif sys.platform == "win32":
        tools = [["clip"]]
    else:
        tools = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]]
    for cmd in tools:
        try:
            proc = subprocess.run(cmd, input=text.encode(),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            continue
        if proc.returncode == 0:
            return True
    return False


class TranscriptionJob:
    def __init__(self, audio, model, mock=False):
        self.audio = audio
        self.model = model
        self.mock  = mock

        self.result: str | Exception | None = None
        self.device: str | None = None
        self.download_pct   = -1.0
        self.model_was_cold = False
        self.model_loaded   = False
        self.decode_secs    = 0.0

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

        repo = self.model.repo

        if not is_model_cached(repo):
            _set_status(repo, render.BUSY)
            self.download_pct = 0.0
            try:
                download_model(repo, progress_cb=lambda pct: setattr(self, "download_pct", pct))
            except Exception as e:
                self.download_pct = -1.0
                _set_status(repo, render.MISSING)
                self.result = e
                self._done.set()
                return
            self.download_pct = -1.0
            _set_status(repo, render.CACHED)

        t0 = time.perf_counter()
        try:
            text, device = transcribe(self.audio, repo, SAMPLE_RATE)
            self.decode_secs  = time.perf_counter() - t0
            self.model_loaded = True
            self.result = text
            self.device = device
            _set_status(repo, render.HOT)
        except Exception as e:
            self.decode_secs = time.perf_counter() - t0
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
        self.notice = ""
        self.type_pos = 0
        self.type_start = 0.0
        self.spin_i = 0
        self.tick = 0

        cfg = _load_cfg()
        saved = cfg.get("model_idx")
        if isinstance(saved, int) and 0 <= saved < len(MODELS):
            self.model_idx = saved
        else:
            self.model_idx = default_model_idx()
        self.show_dev   = bool(cfg.get("show_dev", False))
        self.auto_copy  = bool(cfg.get("auto_copy", False))
        self.typewriter = bool(cfg.get("typewriter", True))

        self._hist = np.zeros(N_BARS, dtype=np.float32)
        self._peak = np.zeros(N_BARS, dtype=np.float32)
        self._smoothed = 0.0
        self._wave_ceil = render.WAVE_CEIL * 0.24
        self.dev_rows = []
        self._job: TranscriptionJob | None = None
        self._captured = None
        self._drain_tick = 0
        self._done_tick  = 0
        self._clipboard_tick = 0
        self._notice_tick = 0
        self._history = collections.deque(transcript_log.load_recent(5), maxlen=5)
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
        self._settings = self._build_settings()

        self.theme = None
        self._last_frame = None
        self._dirty = True

    @property
    def model(self):
        return MODELS[self.model_idx]

    def _clear(self):
        self.scr.clear()
        self._dirty = True

    def _start_job(self, audio, model):
        self._job = TranscriptionJob(audio, model, mock=self._mock)
        self._job.model_was_cold = _get_status(model.repo) != render.HOT
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
                self.state = "idle"; self._clear()
                return True
            if self.state == "done":
                self.transcript = ""; self.err = ""; self.type_pos = 0
                self._hist_idx = -1; self._scroll_offset = 0
                self._append_prefix = ""
                self.state = "idle"; self._clear()
            elif self.state in ("listening", "draining"):
                self.audio.disarm()
                self.state = "idle"
                self._hist[:] = 0.0; self._peak[:] = 0.0; self._clear()
            return True
        if key == curses.KEY_RESIZE:
            self._scroll_offset = 0
            self._clear()
        elif key in (ord('s'), ord('S')):
            self._in_settings = True
            self._settings_row = 0
            self._clear()
        elif key in (ord('h'), ord('H')):
            self.show_dev = not self.show_dev
            _save_state(self)
            if self.show_dev:
                h, w = self.scr.getmaxyx()
                if not render.dev_fits(w, h):
                    self._flash("dev panel needs a taller window")
            self._clear()
        elif key in (ord('m'), ord('M')):
            if self.state not in ("listening", "processing", "draining"):
                self._cycle_model(-1 if key == ord('M') else 1)
        elif key in (ord('a'), ord('A')):
            if self.state == "done" and self.transcript and not self.err:
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
                self._scroll_offset = min(self._scroll_offset + 1, self._max_scroll())
        elif key == ord('['):
            if self.state == "done" and self._history:
                if self._hist_idx == -1:
                    self._hist_current = self.transcript
                if self._hist_idx + 1 < len(self._history):
                    self._hist_idx += 1
                    self._show_history_entry(self._history[self._hist_idx])
        elif key == ord(']'):
            if self.state == "done" and self._hist_idx >= 0:
                self._hist_idx -= 1
                self._show_history_entry(
                    self._hist_current if self._hist_idx == -1 else self._history[self._hist_idx]
                )
        elif key == ord(' '):
            if self.state == "processing":
                if self._job:
                    self._job.cancel()
                self.state = "idle"; self._clear()
                return True
            self._toggle()
        return True

    def _show_history_entry(self, text):
        self.transcript = text
        self.err = ""
        self.type_pos = len(text)
        self._scroll_offset = 0

    def _max_scroll(self, text=None):
        h, w = self.scr.getmaxyx()
        tx_w, rows = render.text_view(w, h, self.show_dev)
        body = self.transcript if text is None else text
        return max(0, len(render.wrap(body, tx_w)) - rows)

    def _handle_settings_key(self, key):
        if key in (27, ord('s'), ord('S'), ord('q'), ord('Q')):
            self._in_settings = False
            self._clear()
        elif key == curses.KEY_UP:
            self._settings_row = max(0, self._settings_row - 1)
        elif key == curses.KEY_DOWN:
            self._settings_row = min(len(self._settings) - 1, self._settings_row + 1)
        elif key in (ord(' '), ord('\n'), curses.KEY_ENTER, 10, 13):
            self._settings[self._settings_row].apply(0)
        elif key == curses.KEY_LEFT:
            self._settings[self._settings_row].apply(-1)
        elif key == curses.KEY_RIGHT:
            self._settings[self._settings_row].apply(+1)
        return True

    def _cycle_model(self, delta):
        if self.state in ("listening", "processing", "draining"):
            return
        self.model_idx = (self.model_idx + (delta or 1)) % len(MODELS)
        _save_state(self)
        _probe_async(self.model.repo)

    def _build_settings(self):
        def toggle_auto_copy(_):
            self.auto_copy = not self.auto_copy
            _save_state(self)

        def toggle_typewriter(_):
            self.typewriter = not self.typewriter
            if not self.typewriter and self.state == "done":
                self.type_pos = len(self.transcript)
            _save_state(self)

        def toggle_dev(_):
            self.show_dev = not self.show_dev
            self._clear()
            _save_state(self)

        return [
            Setting("Model",      "cycle",  lambda: self.model.label,
                    self._cycle_model, [m.label for m in MODELS]),
            Setting("Auto-copy",  "toggle", lambda: self.auto_copy,  toggle_auto_copy),
            Setting("Typewriter", "toggle", lambda: self.typewriter, toggle_typewriter),
            Setting("Dev panel",  "toggle", lambda: self.show_dev,   toggle_dev),
        ]

    def _flash(self, message, frames=90):
        self.notice = message
        self._notice_tick = frames

    def _do_copy(self):
        if _copy_to_clipboard(self.transcript):
            self._clipboard_tick = 45
        else:
            self._flash("no clipboard tool found")

    def _finish_early(self, message):
        """Bail out of a recording without waking the model up."""
        self.state = "done"
        self.err = message
        self.transcript = ""
        self.dev_rows = self._dev_snapshot(None, error=message)
        self.type_pos = 0
        self._done_tick = 0
        self._scroll_offset = 0
        self._append_prefix = ""
        self._clear()

    def _toggle(self):
        if self.state in ("idle", "done"):
            if self.state == "idle":
                self._append_prefix = ""
            try:
                self.audio.arm()
            except MicError as e:
                self._finish_early(str(e))
                return
            self.state = "listening"
            self.transcript = ""; self.err = ""; self.type_pos = 0
            self.dev_rows = []
            self._hist_idx = -1; self._scroll_offset = 0
            self._hist[:] = 0.0; self._peak[:] = 0.0; self._smoothed = 0.0
            self._wave_ceil = render.WAVE_CEIL * 0.24
            self._listen_start = time.perf_counter()
        elif self.state == "listening":
            captured = self.audio.disarm()
            problem  = check_clip(captured)
            if problem:
                self._finish_early(problem)
                return
            self._captured   = captured
            self._drain_tick = 0
            self.state       = "draining"

    def step(self):
        self.tick += 1

        if self._notice_tick > 0:
            self._notice_tick -= 1
            if self._notice_tick == 0:
                self.notice = ""

        if self.state == "processing" and self._job and self._job.is_cancelled():
            self._job = None
            self.state = "idle"
            self._hist[:] = 0.0; self._peak[:] = 0.0
            return

        if self.state == "processing" and self._job and self._job.is_done():
            self._collect(self._job)
            self._job = None

        if self.state == "done":
            self._done_tick += 1
            if self._clipboard_tick > 0:
                self._clipboard_tick -= 1
            if self.typewriter and self.type_pos < len(self.transcript):
                n    = len(self.transcript)
                span = min(TYPE_MAX, max(TYPE_MIN, n * TYPE_DT))
                done = (time.perf_counter() - self.type_start) / span
                self.type_pos = min(n, int(n * done))
                # follow the cursor, or a long transcript types itself straight
                # out the bottom of the viewport
                self._scroll_offset = self._max_scroll(self.transcript[:self.type_pos])

        if self.state in ("processing", "draining"):
            self.spin_i += 1
        if self.state == "processing":
            self._proc_tick += 1

        if self.state == "draining":
            if self._hist.max() >= 0.001:
                n = len(self._hist)
                t = min(1.0, self._drain_tick / 72.0) ** 1.7
                envelope = np.linspace(1.0 - t * 1.04, 1.0 - t * 0.45, n, dtype=np.float32)
                self._hist *= np.clip(envelope, 0.0, 1.0)
            self._drain_tick += 1
            if self._hist.max() < 0.001 or self._drain_tick > 90:
                self._hist[:] = 0.0; self._peak[:] = 0.0
                self.state = "processing"
                self._proc_tick = 0
                self._start_job(self._captured, self.model)

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
            self._hist[:-1] = self._hist[1:]
            self._hist[-1]  = self._smoothed
            self._peak[:-1] = self._peak[1:]
            self._peak[-1]  = self._smoothed
            self._peak = np.maximum(self._hist, self._peak - PEAK_DECAY * self._wave_ceil)

    def _dev_snapshot(self, job, audio_secs=0.0, words=0, error="", stage=""):
        """Three lines, always three lines, so the panel never changes shape."""
        bullet = f" {render.glyph('BULLET')} "
        where  = BACKEND_NAME + (f"{bullet}{job.device}" if job and job.device else "")
        rows   = [("model", f"{job.model.label if job else self.model.label}{bullet}{where}")]

        if error:
            rows.append(("audio", f"{audio_secs:.1f}s"))
            rows.append(("error", error[:44]))
            return rows

        if stage:
            rows.append(("audio", f"{audio_secs:.1f}s" if audio_secs else "-"))
            rows.append(("status", stage))
            return rows

        rows.append(("audio", f"{audio_secs:.1f}s{bullet}{words} words"))
        decode = job.decode_secs if job else 0.0
        if decode > 0:
            ratio = f"{bullet}{audio_secs / decode:.1f}x realtime" if audio_secs else ""
            rows.append(("decode", f"{decode:.1f}s{ratio}"))
        else:
            rows.append(("decode", "-"))
        return rows

    def _collect(self, job):
        res = job.result
        if job.device:
            self._transcribe_device = job.device
        total_secs = len(job.audio) / SAMPLE_RATE

        if isinstance(res, Exception):
            self.err = str(res)
            self.transcript = ""
            self.dev_rows = self._dev_snapshot(job, total_secs, error=str(res))
        else:
            new_text   = (res or "").strip()
            words      = len(new_text.split())
            self._last_word_count = words
            self._last_audio_secs = total_secs
            self.dev_rows = self._dev_snapshot(job, total_secs, words)

            if not new_text:
                self.err = "whisper didn't hear any words in that"
            elif self._append_prefix:
                self.transcript = self._append_prefix + " " + new_text
            else:
                self.transcript = new_text
            self._append_prefix = ""

            if new_text:
                transcript_log.save(self.transcript, job.model.label, total_secs, words)

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

    def _render_state(self, w, h):
        job = self._job
        status = _get_status(self.model.repo)
        device = f" {self._transcribe_device}" if self._transcribe_device else ""
        model_label = f"{self.model.label} {render.status_glyph(status)}{device}"

        if self.state == "processing" and self._captured is not None:
            audio_secs = len(self._captured) / SAMPLE_RATE
        else:
            audio_secs = self._last_audio_secs

        listen_secs = (time.perf_counter() - self._listen_start
                       if self.state == "listening" and self._listen_start else 0.0)

        if self.state == "done" and self.dev_rows:
            dev_rows = self.dev_rows
        elif self.state == "listening":
            dev_rows = self._dev_snapshot(None, listen_secs, stage="recording")
        elif self.state == "draining":
            dev_rows = self._dev_snapshot(None, audio_secs, stage="finishing")
        elif self.state == "processing":
            stage = "downloading" if job and job.download_pct >= 0.0 else "transcribing"
            dev_rows = self._dev_snapshot(job, audio_secs, stage=stage)
        else:
            dev_rows = self._dev_snapshot(None, stage="ready")

        return render.RenderState(
            w=w, h=h,
            state=self.state,
            transcript=self.transcript,
            type_pos=self.type_pos,
            err=self.err,
            tick=self.tick,
            spin_i=self.spin_i,
            hist=self._hist.copy() if self.state in ("listening", "draining") else None,
            show_dev=self.show_dev,
            dev_rows=dev_rows,
            peaks=self._peak.copy() if self.state in ("listening", "draining") else None,
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
            download_label=f"{self.model.label} ({size_label(self.model.mb)})",
            model_missing=status == render.MISSING,
            scroll_offset=self._scroll_offset,
            word_count=self._last_word_count,
            audio_secs=audio_secs,
            listen_secs=listen_secs,
            notice=self.notice,
        )

    def draw(self):
        h, w = self.scr.getmaxyx()

        if w < 60 or h < 18:
            runs = [(max(0, h // 2), 0, f"resize terminal - need 60x18, got {w}x{h}"[:max(1, w - 1)], 0)]
        elif self._in_settings:
            with _model_status_lock:
                status_copy = dict(_model_status)
            ok = crypto_mod.available()
            note = (f"transcripts encrypted  {render.glyph('BULLET')}  {crypto_mod.ENVELOPE_VERSION}"
                    if ok else "encryption unavailable  -  pip install cryptography")
            runs = render.compose_settings(
                w, h, self._settings, self._settings_row, self.theme,
                models=MODELS, model_status=status_copy,
                footnote=note, footnote_ok=ok,
            )
        else:
            runs = render.compose(self._render_state(w, h))

        # before I kept redrawing frames for an IDLE tinytalk... oh god
        frame = (w, h, runs)
        if not self._dirty and frame == self._last_frame:
            return
        self._dirty = False
        self._last_frame = frame

        self.scr.erase()
        for y, x, text, attr in runs:
            try:
                self.scr.addstr(y, x, text, attr)
            except curses.error:
                pass
        try:
            self.scr.move(h - 1, 0)
        except curses.error:
            pass
        self.scr.noutrefresh()
        curses.doupdate()

    def inject_audio(self, path: str):
        try:
            audio = load_file(path)
        except (OSError, RuntimeError) as e:
            self._finish_early(str(e))
            return
        problem = check_clip(audio)
        if problem:
            self._finish_early(problem)
            return
        self._captured = audio
        self.dev_rows = []
        self.state = "processing"
        self._proc_tick = 0
        self._start_job(audio, self.model)

    def run(self, input_path: str | None = None):
        curses.curs_set(0)
        self.scr.nodelay(1)
        self.scr.keypad(1)
        try:
            curses.set_escdelay(50)  # i forgot to change this lol it was 1 second long before
        except (AttributeError, curses.error):
            pass  # i added this because windows-curses and older versions don't support it (to my knowledge)
        if not curses.has_colors():
            raise SystemExit("tinytalk requires a colour terminal")
        curses.start_color()
        curses.use_default_colors()
        self.theme = _build_theme()
        _probe_async(self.model.repo)

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
                self.step()
                self.draw()
                busy = (self.state in ("listening", "draining", "processing")
                        or self._clipboard_tick > 0
                        or self._notice_tick > 0
                        or (self.typewriter and self.type_pos < len(self.transcript)))
                time.sleep(FRAME_DT if busy else IDLE_DT)
        finally:
            self.audio.stop()


# --mock only needs a wall of text to push the wrapping and scrolling around
_MOCK_TEXT = " ".join([
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Duis finibus enim a "
    "sagittis fringilla. Aliquam erat volutpat. Morbi quis nulla condimentum, auctor "
    "diam in, ultricies magna. Curabitur sit amet condimentum dolor. Mauris efficitur "
    "nulla magna, et venenatis libero eleifend eget. Praesent in dapibus lacus, quis "
    "pellentesque urna. Vestibulum ante ipsum primis in faucibus orci luctus."
] * 8)


HELP = """tinytalk - push to talk, transcribed on your own machine

usage:
  tinytalk                    start the recorder
  tinytalk --input FILE       transcribe an audio file instead
  tinytalk log [options]      read back what you've said

options:
  --input FILE   audio or video file to transcribe (needs ffmpeg for non-WAV)
  --model NAME   pick a model for this run: {models}
  --ascii        force the ASCII renderer
  --mock         fake transcription, for poking at the UI
  --version      print the version
  --help         this

files live in {home} (set TINYTALK_HOME to move them)
"""


def _resolve_input(raw: str) -> str:
    """Plain filenames also get looked up in audio-input/, which is where I
    keep test clips."""
    p = Path(raw).expanduser()
    if p.exists() or p.is_absolute():
        return str(p)
    local = Path("audio-input") / raw
    return str(local if local.exists() else p)


def _pick_ascii(cfg, forced):
    if forced:
        return True
    if "ascii" in cfg:
        return bool(cfg["ascii"])
    if sys.platform == "win32":
        return "utf" not in (getattr(sys.stdout, "encoding", "") or "").lower()
    import locale
    try:
        "┌│└".encode(locale.getpreferredencoding(False))
        return False
    except (UnicodeEncodeError, LookupError):
        return True


def main():
    import argparse
    import locale
    import os

    paths.adopt_legacy()

    if len(sys.argv) > 1 and sys.argv[1] == "log":
        from .cli_log import main as log_main
        raise SystemExit(log_main(sys.argv[2:]))

    labels = ", ".join(m.label.lower() for m in MODELS)
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--input", metavar="FILE")
    p.add_argument("--model", metavar="NAME")
    p.add_argument("--ascii", action="store_true")
    p.add_argument("--mock", action="store_true")
    p.add_argument("--version", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    args, unknown = p.parse_known_args()

    if args.help:
        print(HELP.format(models=labels, home=paths.HOME))
        return
    if args.version:
        print(f"tinytalk {__version__}")
        return
    if unknown:
        raise SystemExit(f"tinytalk: don't know what to do with {unknown[0]}  (try --help)")

    if sys.platform == "win32":
        os.system("chcp 65001 >nul 2>&1")
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    # ghostty's terminfo calls box-drawing characters double width, which walks
    # the cursor two columns for every one it should
    if os.environ.get("TERM") == "xterm-ghostty":
        os.environ["TERM"] = "xterm-256color"

    cfg = _load_cfg()
    render.USE_ASCII = _pick_ascii(cfg, args.ascii)

    model_idx = None
    if args.model:
        wanted = args.model.strip().lower()
        model_idx = next((i for i, m in enumerate(MODELS) if m.label.lower() == wanted), None)
        if model_idx is None:
            raise SystemExit(f"tinytalk: no model called {args.model!r}  (pick one of: {labels})")

    input_path = _resolve_input(args.input) if args.input else None

    def boot(scr):
        app = App(scr, mock=args.mock)
        if model_idx is not None:
            app.model_idx = model_idx  # just for this run, don't write it to disk
        app.run(input_path)

    try:
        curses.wrapper(boot)
    except KeyboardInterrupt:
        pass
