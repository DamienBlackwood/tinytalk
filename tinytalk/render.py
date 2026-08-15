import math
import sys
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

USE_ASCII = False

_G_UNICODE = {
    "TL": "┌", "TR": "┐", "BL": "└", "BR": "┘",
    "H": "─", "V": "│",
    "BAR": "█",
    "STEPS": " ▁▂▃▄▅▆▇█",
    "LOWER": " ▔▔▀▀▀▀▀█",
    "SPIN": "◐◓◑◒",
    "REC": " ● REC ",
    "DONE": " ✓ DONE ",
    "IDLE": " ── ",
    "GLASS_H": "─",
    "GLASS_I": "·",
    "BULLET": "·",
    "ARROW": "→",
    "SCROLL_TRACK": "│",
    "SCROLL_THUMB": "█",
    "CHECK": "●",
    "UNCHECK": "○",
    "ARROW_L": "◀",
    "ARROW_R": "▶",
    "CAP_T": "▔", "CAP_B": "▁",
    "ST_MISSING": "✗", "ST_CACHED": "↓", "ST_HOT": "●", "ST_BUSY": "↻", "ST_UNKNOWN": "?",
}
_G_ASCII = {
    "TL": "+", "TR": "+", "BL": "+", "BR": "+",
    "H": "-", "V": "|",
    "BAR": "#",
    "STEPS": " .:-=+*#",
    "LOWER": " .:-=+*#",
    "SPIN": "-\\|/",
    "REC": " REC ",
    "DONE": " DONE ",
    "IDLE": " -- ",
    "GLASS_H": "-",
    "GLASS_I": ".",
    "BULLET": "-",
    "ARROW": "->",
    "SCROLL_TRACK": "|",
    "SCROLL_THUMB": "#",
    "CHECK": "*",
    "UNCHECK": "o",
    "ARROW_L": "<",
    "ARROW_R": ">",
    "CAP_T": "-", "CAP_B": "-",
    "ST_MISSING": "x", "ST_CACHED": "v", "ST_HOT": "*", "ST_BUSY": "~", "ST_UNKNOWN": "?",
}


def _g():
    return _G_ASCII if USE_ASCII else _G_UNICODE


# app.py tracks models as words, not glyphs, so the ascii fallback gets a say
MISSING, CACHED, HOT, BUSY, UNKNOWN = "missing", "cached", "hot", "busy", "unknown"


def status_glyph(status: str) -> str:
    return _g().get("ST_" + status.upper(), _g()["ST_UNKNOWN"])


def glyph(name: str) -> str:
    return _g()[name]


def _pulse(tick, period):
    """0 to 1 and back, on a cosine. everything used to blink on `tick % n < m`,
    which is a square wave, which is why it read as a flicker rather than a
    breath."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * (tick % period) / period)


def _ramp(shades, t):
    return shades[min(len(shades) - 1, max(0, int(t * len(shades))))]


WAVE_CEIL = 0.12

PAD   = 2
BOX_Y = 1

DEV_ROWS   = 3              # always this tall, so the panel never jumps about
DEV_HEIGHT = DEV_ROWS + 2   # rule line, rows, and a gap above the keybinds


def wave_rows(h, show_dev=False):
    """The waveform gives its rows back on a short terminal, and gives more back
    when the dev panel wants some. It used to be a flat 7, which left a 60x18
    window with a header, a footer and nowhere at all to put the transcript."""
    if show_dev:
        h -= DEV_HEIGHT
    if h >= 28:
        return 7
    if h >= 24:
        return 5
    if h >= 21:
        return 3
    return 1


def _header_rows(h, show_dev=False):
    # rail, gap, wordmark, subtitle, gap, chip row, gap, waveform, gap, gap, tag
    return 7 + wave_rows(h, show_dev) + 3


def _box(w, h):
    box_w = max(20, min(w - PAD * 2 - 1, w - PAD))
    box_h = max(6, h - BOX_Y - 1)
    return PAD, BOX_Y, box_w, box_h, PAD + 2, box_w - 4


def _clip(runs, w, h):
    """Last word on where things may be drawn. Everything else in here does its
    own arithmetic; this makes sure none of it can walk off the screen."""
    out = []
    for y, x, text, attr in runs:
        if not text or y < 0 or y >= h or x >= w:
            continue
        if x < 0:
            text, x = text[-x:], 0
        if x + len(text) > w:
            text = text[: w - x]
        if text:
            out.append((y, x, text, attr))
    return out


def _text_rows(w, h, show_dev):
    box_x, box_y, box_w, box_h, ix, iw = _box(w, h)
    top    = box_y + _header_rows(h, show_dev)
    bottom = (box_y + box_h - 2) - 3 - (DEV_HEIGHT if show_dev else 0)
    return top, bottom


def dev_fits(w, h):
    """On a short terminal this used to land on the transcript. Now it stays
    out of the way until there is room for both."""
    top, bottom = _text_rows(w, h, True)
    return bottom - top + 1 >= 2


def text_view(w, h, show_dev=False):
    """Width and height of the transcript viewport. app.py needs the same
    numbers compose() uses for scrolling to land on the right line."""
    show_dev    = show_dev and dev_fits(w, h)
    top, bottom = _text_rows(w, h, show_dev)
    _bx, _by, box_w, _bh, _ix, iw = _box(w, h)
    return max(1, min(72, iw - 4)), max(1, bottom - top + 1)


@dataclass
class Theme:
    dim:       int = 0
    rail:      int = 0
    text:      int = 0
    label:     int = 0
    on:        int = 0
    mid:       int = 0
    soft:      int = 0
    glass:     int = 0
    proc:      int = 0
    proc_mid:  int = 0
    proc_soft: int = 0
    rec:       int = 0
    rec_mid:   int = 0
    rec_soft:  int = 0
    rec_dim:   int = 0
    done:      int = 0
    err:       int = 0

    def rec_ramp(self):
        return (self.rec_dim, self.rec_soft, self.rec_mid, self.rec)

    def proc_ramp(self):
        return (self.proc_soft, self.proc_mid, self.proc)


@dataclass
class RenderState:
    w: int
    h: int
    state: str
    transcript: str
    type_pos: int
    err: str
    tick: int
    spin_i: int
    hist: Optional[np.ndarray]
    show_dev: bool
    version: str
    model: str
    wave_ceil: float
    done_tick: int
    theme: "Theme"
    dev_rows: list = field(default_factory=list)
    peaks: Optional[np.ndarray] = None
    clipboard_tick: int = 0
    auto_copy: bool = False
    hist_idx: int = -1
    hist_len: int = 0
    proc_tick: int = 0
    model_was_cold: bool = False
    model_loaded: bool = False
    download_pct: float = -1.0
    scroll_offset: int = 0
    word_count: int = 0
    audio_secs: float = 0.0
    listen_secs: float = 0.0
    crypto_status: str = ""


def wrap(text, width):
    if not text or width < 1:
        return []
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if len(cand) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _cx(container_w, text):
    return max(0, (container_w - len(text)) // 2)


def chassis(y, x, w, h, label_left, label_right, theme, rail_attr=None):
    runs = []
    g    = _g()
    ra   = rail_attr if rail_attr is not None else theme.rail

    runs.append((y,         x,         g["TL"], ra))
    runs.append((y,         x + w - 1, g["TR"], ra))
    runs.append((y + h - 1, x,         g["BL"], ra))
    runs.append((y + h - 1, x + w - 1, g["BR"], ra))

    ltab       = f" {label_left} " if label_left else ""
    after_left = x + 2 + len(ltab)
    if ltab:
        runs.append((y, x + 2, ltab, theme.label))

    rtab         = f" {label_right} " if label_right else ""
    before_right = x + w - 1
    if rtab:
        rx = x + w - 1 - len(rtab)
        if rx > after_left + 1:
            runs.append((y, rx, rtab, theme.on))
            before_right = rx

    runs.append((y, x + 1, g["H"], ra))
    mid = before_right - after_left
    if mid > 0:
        runs.append((y, after_left, g["H"] * mid, ra))

    runs.append((y + h - 1, x + 1, g["H"] * (w - 2), ra))
    for row in range(y + 1, y + h - 1):
        runs.append((row, x,         g["V"], ra))
        runs.append((row, x + w - 1, g["V"], ra))

    return runs


def _flat(y, x, w, h, attr):
    g = _g()
    return [(y + h // 2, x, g["GLASS_H"] * w, attr)]


def waveform_idle(y, x, w, h, theme, tick):
    g = _g()
    return [(y + h // 2, x, g["GLASS_H"] * w, theme.glass)]


def waveform_done(y, x, w, h, theme):
    g = _g()
    return [(y + h // 2, x, g["GLASS_H"] * w, theme.glass)]


def waveform_processing(y, x, w, h, theme, tick, proc_tick=0):
    BAR_W, GAP = 2, 1
    stride  = BAR_W + GAP
    n_slots = max(1, w // stride)

    PERIOD = 150
    head   = (tick % PERIOD) / PERIOD * n_slots
    SIGMA  = max(2.0, n_slots / 7.0)

    # cleaned up the transition
    fade_in = min(1.0, proc_tick / 30.0)
    fade_in = 1.0 - (1.0 - fade_in) ** 3

    levels = np.zeros(n_slots, dtype=np.float32)
    for i in range(n_slots):
        d = i - head
        t = max(
            float(np.exp(-0.5 * (d / SIGMA) ** 2)),
            float(np.exp(-0.5 * ((d - n_slots) / SIGMA) ** 2)),
            float(np.exp(-0.5 * ((d + n_slots) / SIGMA) ** 2)),
        )
        levels[i] = t

    recency = np.linspace(0.3, 1.0, n_slots, dtype=np.float32)
    levels  = levels * recency * fade_in

    grid = [[" "] * w for _ in range(h)]
    attr = [[0]   * w for _ in range(h)]
    _draw_bars(grid, attr, h, levels, recency, theme, processing=True)
    return _grid_to_runs(y, x, grid, attr)


def _pool(src, n_slots):
    """Squash the history buffer down to however many bars fit."""
    src = src.astype(np.float32, copy=False)
    if len(src) == n_slots:
        return src
    if len(src) > n_slots:
        trim = src[len(src) - (len(src) // n_slots) * n_slots:]
        if len(trim) >= n_slots:
            return trim.reshape(n_slots, -1).max(axis=1)
    return np.interp(np.linspace(0, 1, n_slots), np.linspace(0, 1, len(src)), src)


def waveform_active(y, x, w, h, hist, theme, wave_ceil=WAVE_CEIL, peaks=None):
    if hist is None or len(hist) == 0:
        return _flat(y, x, w, h, theme.glass)

    BAR_W, GAP = 2, 1
    n_slots = max(1, w // (BAR_W + GAP))

    ceil   = max(WAVE_CEIL * 0.16, wave_ceil)
    levels = np.clip(_pool(hist, n_slots) / ceil, 0.0, 1.0) ** 0.75
    caps   = (np.clip(_pool(peaks, n_slots) / ceil, 0.0, 1.0) ** 0.75
              if peaks is not None and len(peaks) else None)

    recency = np.linspace(0.15, 1.0, n_slots, dtype=np.float32)

    grid = [[" "] * w for _ in range(h)]
    attr = [[0]   * w for _ in range(h)]
    _draw_bars(grid, attr, h, levels, recency, theme, processing=False, caps=caps)
    return _grid_to_runs(y, x, grid, attr)


def _draw_bars(grid, attr, h, levels, recency, theme, processing=False, caps=None):
    BAR_W, GAP = 2, 1
    stride  = BAR_W + GAP
    n_slots = len(levels)
    w       = len(grid[0])
    cx      = h // 2
    g       = _g()
    steps   = len(g["STEPS"]) - 1
    lower   = g["LOWER"]

    for col in range(w):
        grid[cx][col] = g["GLASS_H"]
        attr[cx][col] = theme.glass

    for i in range(n_slots):
        lv = float(levels[i])
        if lv <= 0.0:
            continue

        col0 = i * stride
        if col0 + BAR_W > w:
            break

        rec = float(recency[i])
        if processing:
            bar_color = theme.proc if rec > 0.55 else theme.proc_soft
        elif rec > 0.70:
            bar_color = theme.on
        elif rec > 0.35:
            bar_color = theme.mid
        else:
            bar_color = theme.soft

        units      = lv * max(1, cx - 1) * steps
        full_cells = int(units // steps)
        rem        = int(round(units - full_cells * steps))
        cols       = range(col0, col0 + BAR_W)

        for d in range(1, full_cells + 1):
            for row in (cx - d, cx + d):
                if 0 <= row < h:
                    for col in cols:
                        grid[row][col] = g["BAR"]
                        attr[row][col] = bar_color

        if rem > 0:
            top = cx - full_cells - 1
            if top >= 0:
                for col in cols:
                    grid[top][col] = g["STEPS"][rem]
                    attr[top][col] = bar_color
            bottom = cx + full_cells + 1
            if bottom < h:
                ch = lower[min(rem, len(lower) - 1)]
                for col in cols:
                    grid[bottom][col] = ch
                    attr[bottom][col] = bar_color

        # peak hold. I need to tweak this more
        if caps is not None:
            cap_cells = int(float(caps[i]) * max(1, cx - 1) * steps // steps)
            if cap_cells > full_cells:
                for row, ch in ((cx - cap_cells, g["CAP_T"]), (cx + cap_cells, g["CAP_B"])):
                    if 0 <= row < h and grid[row][col0] == " ":
                        for col in cols:
                            grid[row][col] = ch
                            attr[row][col] = theme.soft


def _grid_to_runs(y, x, chars, attrs):
    runs = []
    for row, (cline, aline) in enumerate(zip(chars, attrs)):
        if not cline:
            continue
        cur_attr = aline[0]
        cur_buf  = [cline[0]]
        cur_x    = x
        for i in range(1, len(cline)):
            if aline[i] == cur_attr:
                cur_buf.append(cline[i])
            else:
                runs.append((y + row, cur_x, "".join(cur_buf), cur_attr))
                cur_x    = x + i
                cur_attr = aline[i]
                cur_buf  = [cline[i]]
        runs.append((y + row, cur_x, "".join(cur_buf), cur_attr))
    return runs


def _chip_text(state, spin_i):
    g = _g()
    if state == "listening":
        return g["REC"]
    if state == "processing":
        return f" {g['SPIN'][(spin_i // 8) % 4]} "
    if state == "done":
        return g["DONE"]
    return g["IDLE"]


def _scrollbar(y0, height, total_lines, visible_lines, offset, x, theme):
    if total_lines <= visible_lines or height < 2:
        return []
    g = _g()
    runs = []
    track_h = height
    thumb_h = max(1, round(track_h * visible_lines / total_lines))
    thumb_top = round(track_h * offset / total_lines)
    thumb_top = min(thumb_top, track_h - thumb_h)
    for i in range(track_h):
        ch   = g["SCROLL_THUMB"] if thumb_top <= i < thumb_top + thumb_h else g["SCROLL_TRACK"]
        attr = theme.mid if thumb_top <= i < thumb_top + thumb_h else theme.dim
        runs.append((y0 + i, x, ch, attr))
    return runs


_SETTING_HINTS = {
    "Model":      "larger = more accurate, slower",
    "Auto-copy":  "copy to clipboard automatically when done",
    "Typewriter": "animate text character by character",
    "Dev panel":  "show timing info",
}


def compose_settings(w, h, items, selected_row, theme, models=None, model_status=None, crypto_status=""):
    runs = []
    g    = _g()

    box_x, box_y, box_w, box_h, ix, iw = _box(w, h)

    runs.extend(chassis(box_y, box_x, box_w, box_h, "TINYTALK", "SETTINGS", theme))

    cur_y = box_y + 2
    title = "S E T T I N G S"
    runs.append((cur_y, box_x + _cx(box_w, title), title, theme.text))
    cur_y += 1
    ud, lr = ("up/dn", "l/r") if USE_ASCII else ("↑ ↓", "← →")
    subs = [
        f"{ud}  navigate    {lr}  cycle model    SPC / ENT  toggle    ESC  close",
        f"{ud}  navigate    {lr}  cycle    SPC  toggle    ESC  close",
        f"{ud} move   SPC toggle   ESC close",
    ]
    sub = next((s for s in subs if len(s) <= box_w - 2), subs[-1])
    runs.append((cur_y, box_x + _cx(box_w, sub), sub, theme.dim))
    cur_y += 2

    inner_x = ix + 1
    inner_w = iw - 2
    ctrl_w  = 16

    for i, item in enumerate(items):
        label, kind, getter, options = item.label, item.kind, item.getter, item.options
        row_y    = cur_y + i * 2
        is_sel   = i == selected_row
        lbl_attr = theme.text  if is_sel else theme.label
        dim_attr = theme.label if is_sel else theme.dim

        if is_sel:
            runs.append((row_y, inner_x, " " * inner_w, theme.glass))

        runs.append((row_y, inner_x + 2, label, lbl_attr))

        hint     = _SETTING_HINTS.get(label, "")
        hint_x   = inner_x + 2 + len(label) + 2
        hint_end = inner_x + inner_w - ctrl_w - 1
        if hint_end > hint_x and hint:
            runs.append((row_y, hint_x, hint[: hint_end - hint_x], dim_attr))

        ctrl_x = inner_x + inner_w - ctrl_w

        if kind == "toggle":
            val       = getter()
            chip      = "[ ON  ]" if val else "[ OFF ]"
            chip_attr = theme.done if val else theme.soft
            runs.append((row_y, ctrl_x + (ctrl_w - len(chip)) // 2, chip, chip_attr))

        elif kind == "cycle":
            val = getter()
            if label == "Model" and models is not None:
                repo   = next((m.repo for m in models if m.label == val), None)
                status = status_glyph((model_status or {}).get(repo, UNKNOWN)) if repo else ""
                inner  = f"{val} {status}".strip()
            else:
                inner = val
            if is_sel:
                chip = f"{g['ARROW_L']} {inner} {g['ARROW_R']}"
            else:
                chip = f"  {inner}  "
            chip_attr = theme.on if is_sel else theme.mid
            runs.append((row_y, ctrl_x + max(0, (ctrl_w - len(chip)) // 2), chip, chip_attr))

        if i < len(items) - 1:
            runs.append((row_y + 1, ix + 1, g["H"] * (iw - 2), theme.dim))

    foot_y = box_y + box_h - 2

    if crypto_status:
        info_y    = foot_y - 1
        info_attr = theme.done if "active" in crypto_status else theme.dim
        runs.append((info_y, box_x + _cx(box_w, crypto_status),
                     crypto_status, info_attr))

    runs.append((foot_y, box_x + _cx(box_w, "S or ESC to close"),
                 "S or ESC to close", theme.dim))

    return _clip(runs, w, h)


def _download_bar(pct: float, width: int, theme, tick: int):
    g       = _g()
    filled  = int(pct * width)
    bar     = []

    BLOCKS  = " ░▒▓█"
    FULL    = BLOCKS[-1]
    EMPTY   = BLOCKS[0]

    for i in range(width):
        if i < filled - 1:
            bar.append(FULL if not USE_ASCII else "#")
        elif i == filled - 1:
            sub = int((pct * width - filled) * (len(BLOCKS) - 1))
            bar.append(BLOCKS[max(0, min(sub + 2, len(BLOCKS) - 1))] if not USE_ASCII else "#")
        else:
            bar.append(EMPTY if not USE_ASCII else ".")

    return "".join(bar)


def compose(rs: RenderState):
    runs = []
    g = _g()

    w, h           = rs.w, rs.h
    state          = rs.state
    transcript     = rs.transcript
    type_pos       = rs.type_pos
    err            = rs.err
    tick           = rs.tick
    spin_i         = rs.spin_i
    hist           = rs.hist
    show_dev       = rs.show_dev and dev_fits(rs.w, rs.h)
    version        = rs.version
    model          = rs.model
    wave_ceil      = rs.wave_ceil
    done_tick      = rs.done_tick
    theme          = rs.theme
    clipboard_tick = rs.clipboard_tick
    auto_copy      = rs.auto_copy
    hist_idx       = rs.hist_idx
    hist_len       = rs.hist_len
    model_was_cold = rs.model_was_cold
    model_loaded   = rs.model_loaded
    download_pct   = rs.download_pct
    scroll_offset  = rs.scroll_offset
    word_count     = rs.word_count
    audio_secs     = rs.audio_secs
    listen_secs    = rs.listen_secs
    proc_tick      = rs.proc_tick

    box_x, box_y, box_w, box_h, ix, iw = _box(w, h)

    chassis_runs = chassis(box_y, box_x, box_w, box_h, "TINYTALK", model, theme)

    cur_y = box_y + 2

    mark      = "T I N Y T A L K"
    mark_attr = theme.mid if state == "processing" else theme.text
    runs.append((cur_y, box_x + _cx(box_w, mark), mark, mark_attr))
    cur_y += 1

    backend = "mlx" if sys.platform == "darwin" else "faster-whisper"
    sub = f"on-device transcription {g['BULLET']} whisper {g['BULLET']} {backend} {g['BULLET']} {version}"
    runs.append((cur_y, box_x + _cx(box_w, sub), sub, theme.label))
    cur_y += 2

    chip = _chip_text(state, spin_i)
    if state in ("listening", "draining"):
        chip_col = _ramp(theme.rec_ramp(), _pulse(tick, 64))
    elif state == "processing":
        chip_col = theme.proc
    elif state == "done":
        chip_col = _ramp((theme.soft, theme.mid, theme.done), min(1.0, done_tick / 22.0))
    else:
        chip_col = theme.label

    runs.append((cur_y, ix,                       f"IN {g['ARROW']} MIC", theme.label))
    runs.append((cur_y, box_x + _cx(box_w, chip), chip,                   chip_col))
    runs.append((cur_y, ix + iw - len("SR 16K"),  "SR 16K",               theme.label))
    cur_y += 2

    wave_w = min(iw - 2, 140)
    wave_x = box_x + _cx(box_w, " " * wave_w)
    wave_y = cur_y
    wave_h = wave_rows(rs.h, show_dev)

    if download_pct >= 0.0:
        cur_y += 2
    else:
        if state in ("listening", "draining"):
            runs.extend(waveform_active(wave_y, wave_x, wave_w, wave_h, hist, theme,
                                        wave_ceil, peaks=rs.peaks))
        elif state == "processing":
            runs.extend(waveform_processing(wave_y, wave_x, wave_w, wave_h, theme, tick, proc_tick))
        elif state == "done":
            runs.extend(waveform_done(wave_y, wave_x, wave_w, wave_h, theme))
        else:
            runs.extend(waveform_idle(wave_y, wave_x, wave_w, wave_h, theme, tick))
        cur_y += wave_h + 2

    tx_w, _ = text_view(rs.w, rs.h, show_dev)
    tx_x     = box_x + _cx(box_w, " " * (tx_w + 2))
    sb_x     = tx_x + tx_w + 1

    foot_y     = box_y + box_h - 2
    text_max_y = foot_y - 3 - (DEV_HEIGHT if show_dev else 0)

    if state == "done" and (transcript or err):
        tag      = "TRANSCRIPT" if not err else "ERROR"
        tag_attr = (theme.err  if err else
                    theme.label if done_tick > 12 else theme.soft)
        runs.append((cur_y, box_x + _cx(box_w, tag), tag, tag_attr))
        if hist_idx >= 0 and hist_len > 0:
            badge = f"[{hist_idx + 1}/{hist_len}]"
            runs.append((cur_y, tx_x + tx_w - len(badge), badge, theme.soft))
        cur_y += 1

    if err and state == "done":
        err_lines = wrap(err, tx_w)[:3]
        for i, line in enumerate(err_lines):
            runs.append((cur_y + i, tx_x, line, theme.err))
        cur_y += len(err_lines)

    elif transcript and state == "done":
        txt_attr      = theme.text if done_tick > 2 else theme.mid
        all_lines     = wrap(transcript[:type_pos], tx_w)
        visible_h     = max(1, text_max_y - cur_y + 1)
        total_lines   = len(all_lines)
        max_offset    = max(0, total_lines - visible_h)
        scroll_offset = min(scroll_offset, max_offset)
        visible_lines = all_lines[scroll_offset: scroll_offset + visible_h]

        for i, line in enumerate(visible_lines):
            runs.append((cur_y + i, tx_x, line, txt_attr))

        if total_lines > visible_h:
            runs.extend(_scrollbar(cur_y, visible_h, total_lines, visible_h, scroll_offset, sb_x, theme))

        if type_pos < len(transcript) and visible_lines:
            cursor_vis = (total_lines - 1) - scroll_offset
            if 0 <= cursor_vis < len(visible_lines) and (tick // 32) % 2 == 0:
                runs.append((cur_y + cursor_vis, tx_x + len(visible_lines[cursor_vis]), "|", theme.on))

        cur_y += min(total_lines, visible_h)

    elif state == "idle":
        if "✗" in model:
            hint  = "press SPACE to speak  -  model downloads automatically"
            hint2 = "make sure you've run:  hf auth login"
            runs.append((cur_y, box_x + _cx(box_w, hint), hint, theme.label))
            cur_y += 1
            runs.append((cur_y, box_x + _cx(box_w, hint2), hint2, theme.dim))
            cur_y += 1
        else:
            hint = "press SPACE to speak"
            runs.append((cur_y, box_x + _cx(box_w, hint), hint, theme.label))
            cur_y += 1
    elif state == "listening":
        mins, secs = divmod(int(listen_secs), 60)
        timer = f"{mins}:{secs:02d}"
        line  = f"SPACE to stop  {g['BULLET']}  {timer}"
        runs.append((cur_y, box_x + _cx(box_w, line), line, theme.label))
        cur_y += 1
    elif state == "processing":
        proc_attr = _ramp(theme.proc_ramp(), _pulse(tick, 72))
        if download_pct >= 0.0:
            bar_w    = min(40, iw - 8)
            bar_str  = _download_bar(download_pct, bar_w, theme, tick)
            pct_str  = f"{int(download_pct * 100):3d}%"
            label    = f"downloading  {pct_str}"
            runs.append((cur_y, box_x + _cx(box_w, label), label, proc_attr))
            cur_y += 1
            bar_x    = box_x + _cx(box_w, bar_str)
            filled_n = int(download_pct * bar_w)
            if filled_n > 0:
                runs.append((cur_y, bar_x, bar_str[:filled_n], theme.done))
            if filled_n < bar_w:
                runs.append((cur_y, bar_x + filled_n, bar_str[filled_n:], theme.dim))
            cur_y += 1
            sub = "this only happens once"
            runs.append((cur_y, box_x + _cx(box_w, sub), sub, theme.dim))
            cur_y += 1
        else:
            base = "loading model" if (model_was_cold and not model_loaded) else "transcribing"
            if audio_secs > 0:
                unit    = "second" if 0.95 <= audio_secs < 1.05 else "seconds"
                audio_s = f"  {g['BULLET']}  {audio_secs:.1f} {unit} long"
            else:
                audio_s = ""
            label = base + audio_s
            runs.append((cur_y, box_x + _cx(box_w, label), label, proc_attr))
            cur_y += 1
            if proc_tick > 180:
                elapsed = proc_tick / 60.0
                hint    = f"still working  {g['BULLET']}  {elapsed:.0f}s elapsed"
                runs.append((cur_y, box_x + _cx(box_w, hint), hint, theme.dim))
                cur_y += 1

    stat_y = min(cur_y, text_max_y + 1)
    if state == "done" and not err and word_count > 0 and not show_dev:
        stat      = f"{word_count} words  {g['BULLET']}  {audio_secs:.1f}s"
        stat_attr = theme.dim if done_tick > 40 else theme.soft
        runs.append((stat_y, box_x + _cx(box_w, stat), stat, stat_attr))

    if state == "done" and clipboard_tick > 0:
        cb_attr = theme.done if clipboard_tick > 22 else theme.mid
        cb_y    = stat_y + 1
        if cb_y < foot_y:
            runs.append((cb_y, box_x + _cx(box_w, "copied"), "copied", cb_attr))

    if show_dev:
        # this used to be anchored to the bottom rail, so the last two lines of it landed on the keybinds and the rail
        rows = (list(rs.dev_rows) + [("", "")] * DEV_ROWS)[:DEV_ROWS]
        dy   = foot_y - DEV_ROWS - 2
        rule = f"{g['H']}{g['H']} DEV " + g["H"] * max(0, iw - 9)
        runs.append((dy, ix + 2, rule, theme.label))
        pad = max((len(k) for k, _ in rows if k), default=0)
        for i, (key, val) in enumerate(rows):
            if not key:
                continue
            runs.append((dy + 1 + i, ix + 4, key.ljust(pad), theme.soft))
            runs.append((dy + 1 + i, ix + 4 + pad + 3, str(val)[:iw - 10 - pad], theme.mid))

    arrows = "u/d" if USE_ASCII else "↑↓"
    kmap = {
        "idle":       [("SPC", "record"), ("m/M", "model"), ("S", "settings"), ("H", "dev"), ("Q", "quit")],
        "done":       [("SPC", "again"), ("A", "append"), ("C", "copy"), (arrows, "scroll"),
                       ("[/]", "history"), ("S", "settings"), ("ESC", "clear")],
        "listening":  [("SPC", "stop"), ("ESC", "cancel"), ("Q", "quit")],
        "processing": [("SPC", "cancel"), ("ESC", "cancel")],
    }
    # narrow terminals lose the rightmost hints
    sep   = f"  {g['BULLET']}  "
    parts = [f"{k} {v}" for k, v in kmap.get(state, [])]
    while len(parts) > 1 and len(sep.join(parts)) > iw:
        parts.pop()
    line = sep.join(parts)
    runs.append((foot_y, box_x + _cx(box_w, line), line, theme.dim))

    runs.extend(chassis_runs)
    return _clip(runs, rs.w, rs.h)
