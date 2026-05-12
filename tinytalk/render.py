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
}
_G_ASCII = {
    "TL": "+", "TR": "+", "BL": "+", "BR": "+",
    "H": "-", "V": "|",
    "BAR": "#",
    "STEPS": " .:-=+*#",
    "LOWER": "#*+=-::.. ",
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
}


def _g():
    return _G_ASCII if USE_ASCII else _G_UNICODE


WAVE_CEIL = 0.12


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
    proc_soft: int = 0
    rec:       int = 0
    done:      int = 0
    err:       int = 0


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
    dev_log: list
    version: str
    model: str
    wave_ceil: float
    done_tick: int
    theme: "Theme"
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
    if not text:
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
    after_left = x + 1 + len(ltab)
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


def waveform_active(y, x, w, h, hist, theme, wave_ceil=WAVE_CEIL):
    if hist is None or len(hist) == 0:
        return _flat(y, x, w, h, theme.glass)

    BAR_W, GAP = 2, 1
    stride  = BAR_W + GAP
    n_slots = max(1, w // stride)

    src = hist.astype(np.float32, copy=False)
    if len(src) == n_slots:
        pooled = src
    elif len(src) > n_slots:
        trim = src[len(src) - (len(src) // n_slots) * n_slots:]
        pooled = trim.reshape(n_slots, -1).mean(axis=1) if len(trim) >= n_slots else \
                 np.interp(np.linspace(0, 1, n_slots), np.linspace(0, 1, len(src)), src)
    else:
        pooled = np.interp(np.linspace(0, 1, n_slots), np.linspace(0, 1, len(src)), src)

    ceil   = max(WAVE_CEIL * 0.16, wave_ceil)
    levels = np.clip(pooled / ceil, 0.0, 1.0) ** 0.75

    recency = np.linspace(0.15, 1.0, n_slots, dtype=np.float32)

    grid = [[" "] * w for _ in range(h)]
    attr = [[0]   * w for _ in range(h)]
    _draw_bars(grid, attr, h, levels, recency, theme, processing=False)
    return _grid_to_runs(y, x, grid, attr)


def _draw_bars(grid, attr, h, levels, recency, theme, processing=False):
    BAR_W, GAP = 2, 1
    stride  = BAR_W + GAP
    n_slots = len(levels)
    w       = len(grid[0])
    cx      = h // 2
    g       = _g()
    steps   = len(g["STEPS"]) - 1

    for col in range(w):
        grid[cx][col] = g["GLASS_H"]
        attr[cx][col] = theme.glass

    for i in range(n_slots):
        lv  = float(levels[i])
        rec = float(recency[i])
        if lv <= 0.0:
            continue

        col0 = i * stride
        if col0 + BAR_W > w:
            break

        if processing:
            bar_color = theme.proc if rec > 0.55 else theme.proc_soft
        else:
            if rec > 0.70:
                bar_color = theme.on
            elif rec > 0.35:
                bar_color = theme.mid
            else:
                bar_color = theme.soft

        top_h_units = lv * (cx - 1) * steps
        full_cells  = int(top_h_units // steps)
        rem         = int(round(top_h_units - full_cells * steps))

        for d in range(1, full_cells + 1):
            row = cx - d
            if row < 0:
                break
            for bx in range(BAR_W):
                grid[row][col0 + bx] = g["BAR"]
                attr[row][col0 + bx] = bar_color

        if rem > 0:
            row = cx - full_cells - 1
            if row >= 0:
                ch = g["STEPS"][rem]
                for bx in range(BAR_W):
                    grid[row][col0 + bx] = ch
                    attr[row][col0 + bx] = bar_color

        for d in range(1, full_cells + 1):
            row = cx + d
            if row >= h:
                break
            for bx in range(BAR_W):
                grid[row][col0 + bx] = g["BAR"]
                attr[row][col0 + bx] = bar_color

        if rem > 0:
            row = cx + full_cells + 1
            if row < h:
                ch = g["LOWER"][min(rem, len(g["LOWER"]) - 1)]
                for bx in range(BAR_W):
                    grid[row][col0 + bx] = ch
                    attr[row][col0 + bx] = bar_color


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
        return f" {g['SPIN'][(spin_i // 6) % 4]} "
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

    PAD   = 2
    box_x = PAD
    box_y = 1
    box_w = max(60, w - PAD * 2 - 1)
    box_h = max(6, h - box_y - 1)
    ix    = box_x + 2
    iw    = box_w - 4

    runs.extend(chassis(box_y, box_x, box_w, box_h, "TINYTALK", "SETTINGS", theme))

    cur_y = box_y + 2
    title = "S E T T I N G S"
    runs.append((cur_y, box_x + _cx(box_w, title), title, theme.text))
    cur_y += 1
    sub = "↑ ↓  navigate    ← →  cycle model    SPC / ENT  toggle    ESC  close"
    runs.append((cur_y, box_x + _cx(box_w, sub), sub, theme.dim))
    cur_y += 2

    inner_x = ix + 1
    inner_w = iw - 2
    ctrl_w  = 16

    for i, (label, kind, getter, options) in enumerate(items):
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
                cur_mid = next((m[0] for m in models if m[1] == val), None)
                status  = (model_status or {}).get(cur_mid, "?") if cur_mid else ""
                inner   = f"{val} {status}".strip()
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

    return runs


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
    show_dev       = rs.show_dev
    dev_log        = rs.dev_log
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

    PAD   = 2
    box_x = PAD
    box_y = 1
    box_w = max(60, w - PAD * 2 - 1)
    box_h = max(6, h - box_y - 1)
    ix    = box_x + 2
    iw    = box_w - 4

    rail_attr = theme.rail

    chassis_runs = chassis(box_y, box_x, box_w, box_h, "TINYTALK", model, theme, rail_attr)

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
        chip_col = theme.rec if (tick % 50) < 35 else theme.mid
    elif state == "processing":
        chip_col = theme.proc
    elif state == "done":
        chip_col = theme.done if done_tick > 20 else (theme.mid if done_tick > 8 else theme.soft)
    else:
        chip_col = theme.label

    runs.append((cur_y, ix,                       f"IN {g['ARROW']} MIC", theme.label))
    runs.append((cur_y, box_x + _cx(box_w, chip), chip,                   chip_col))
    runs.append((cur_y, ix + iw - len("SR 16K"),  "SR 16K",               theme.label))
    cur_y += 2

    WH     = 7
    wave_w = min(iw - 2, 140)
    wave_x = box_x + _cx(box_w, " " * wave_w)
    wave_y = cur_y

    if download_pct >= 0.0:
        cur_y += 2
    elif state in ("listening", "draining"):
        runs.extend(waveform_active(wave_y, wave_x, wave_w, WH, hist, theme, wave_ceil))
        cur_y += WH + 2
    elif state == "processing":
        runs.extend(waveform_processing(wave_y, wave_x, wave_w, WH, theme, tick, proc_tick))
        cur_y += WH + 2
    elif state == "done":
        runs.extend(waveform_done(wave_y, wave_x, wave_w, WH, theme))
        cur_y += WH + 2
    else:
        runs.extend(waveform_idle(wave_y, wave_x, wave_w, WH, theme, tick))
        cur_y += WH + 2

    tx_w = min(72, iw - 4)
    tx_x = box_x + _cx(box_w, " " * (tx_w + 2))
    sb_x = tx_x + tx_w + 1

    foot_y     = box_y + box_h - 2
    text_max_y = foot_y - 3

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
        runs.append((cur_y, tx_x, ("! " + err)[:tx_w], theme.err))
        cur_y += 1
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
            all_typed  = wrap(transcript[:type_pos], tx_w)
            cursor_abs = max(0, len(all_typed) - 1)
            cursor_vis = cursor_abs - scroll_offset
            if 0 <= cursor_vis < len(visible_lines):
                last = visible_lines[cursor_vis]
                if (tick // 20) % 2 == 0:
                    runs.append((cur_y + cursor_vis, tx_x + len(last), "|", theme.on))

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
        proc_attr = theme.proc if (tick % 40) < 28 else theme.proc_soft
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
            base    = "loading model" if (model_was_cold and not model_loaded) else "transcribing"
            audio_s = f"  {g['BULLET']}  {audio_secs:.1f}s" if audio_secs > 0 else ""
            label   = base + audio_s
            runs.append((cur_y, box_x + _cx(box_w, label), label, proc_attr))
            cur_y += 1
            if proc_tick > 180:
                elapsed = proc_tick / 60.0
                hint    = f"still working  {g['BULLET']}  {elapsed:.0f}s elapsed"
                runs.append((cur_y, box_x + _cx(box_w, hint), hint, theme.dim))
                cur_y += 1

    stat_y = min(cur_y, text_max_y + 1)
    if state == "done" and word_count > 0:
        stat      = f"{word_count} words  {g['BULLET']}  {audio_secs:.1f}s"
        stat_attr = theme.dim if done_tick > 40 else theme.soft
        runs.append((stat_y, box_x + _cx(box_w, stat), stat, stat_attr))

    if state == "done" and clipboard_tick > 0:
        cb_attr = theme.done if clipboard_tick > 22 else theme.mid
        cb_y    = stat_y + 1
        if cb_y < foot_y:
            runs.append((cb_y, box_x + _cx(box_w, "copied"), "copied", cb_attr))

    if show_dev and dev_log:
        dy = box_y + box_h - 1 - len(dev_log)
        runs.append((dy, ix + 2, f"{g['H']}{g['H']} DEV " + g["H"] * max(0, iw - 9), theme.label))
        for i, line in enumerate(dev_log):
            runs.append((dy + 1 + i, ix + 4, line[:iw - 6], theme.dim))

    kmap = {
        "idle":       [("SPC", "record"), ("m/M", "model"), ("S", "settings"), ("H", "dev"), ("Q", "quit")],
        "done":       [("SPC", "again"), ("A", "append"), ("m/M", "model"), ("C", "copy"), ("↑↓", "scroll"), ("[/]", "hist"), ("S", "settings"), ("ESC", "clear")],
        "listening":  [("SPC", "stop"), ("ESC", "cancel"), ("Q", "quit")],
        "processing": [("SPC", "cancel"), ("ESC", "cancel")],
    }
    parts = [f"{k} {v}" for k, v in kmap.get(state, [])]
    sep   = f"  {g['BULLET']}  "
    runs.append((foot_y, box_x + _cx(box_w, sep.join(parts)), sep.join(parts), theme.dim))

    runs.extend(chassis_runs)
    return runs
