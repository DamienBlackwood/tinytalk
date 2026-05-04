import math
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
}


def _g():
    return _G_ASCII if USE_ASCII else _G_UNICODE


WAVE_CEIL = 0.12


class Theme:
    pass


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
    ch = g["GLASS_H"] if (tick // 50) % 2 == 0 else g["GLASS_I"]
    return [(y + h // 2, x, ch * w, theme.glass)]


def waveform_done(y, x, w, h, theme):
    g = _g()
    return [(y + h // 2, x, g["GLASS_H"] * w, theme.glass)]


def waveform_processing(y, x, w, h, theme, tick):
    BAR_W, GAP = 2, 1
    stride  = BAR_W + GAP
    n_slots = max(1, w // stride)

    PERIOD = 150
    head   = (tick % PERIOD) / PERIOD * n_slots
    SIGMA  = max(2.0, n_slots / 7.0)

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
    levels  = levels * recency

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

# I have plans to change this soon.
def compose(w, h, state, transcript, type_pos, err, tick, spin_i, hist,
            show_dev, dev_log, version, model, wave_ceil, done_tick, theme,
            clipboard_tick=0, auto_copy=False, hist_idx=-1, hist_len=0,
            proc_tick=0, model_was_cold=False):
    runs = []
    g = _g()

    PAD   = 2
    box_x = PAD
    box_y = 1
    box_w = max(60, w - PAD * 2 - 1)
    box_h = max(6, h - box_y - 1)
    ix    = box_x + 2
    iw    = box_w - 4

    breathe   = 0.5 + 0.5 * math.sin(tick / 55.0)
    rail_attr = theme.glass if state == "idle" and breathe < 0.4 else theme.rail

    chassis_runs = chassis(box_y, box_x, box_w, box_h, "TINYTALK", model, theme, rail_attr)

    cur_y = box_y + 2

    mark      = "T I N Y T A L K"
    mark_attr = theme.mid if state == "processing" else theme.text
    runs.append((cur_y, box_x + _cx(box_w, mark), mark, mark_attr))
    cur_y += 1

    sub = f"on-device transcription {g['BULLET']} whisper {g['BULLET']} mlx {g['BULLET']} {version}"
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

    if state in ("listening", "draining"):
        runs.extend(waveform_active(wave_y, wave_x, wave_w, WH, hist, theme, wave_ceil))
    elif state == "processing":
        runs.extend(waveform_processing(wave_y, wave_x, wave_w, WH, theme, tick))
    elif state == "done":
        runs.extend(waveform_done(wave_y, wave_x, wave_w, WH, theme))
    else:
        runs.extend(waveform_idle(wave_y, wave_x, wave_w, WH, theme, tick))

    cur_y += WH + 2

    tx_w = min(72, iw - 2)
    tx_x = box_x + _cx(box_w, " " * tx_w)

    if state == "done" and (transcript or err):
        tag      = "TRANSCRIPT" if not err else "ERROR"
        tag_attr = (theme.err  if err else
                    theme.label if done_tick > 12 else theme.soft)
        runs.append((cur_y, box_x + _cx(box_w, tag), tag, tag_attr))
        if hist_idx >= 0 and hist_len > 0:
            badge = f"{hist_idx + 1}/{hist_len}"
            runs.append((cur_y, tx_x + tx_w - len(badge), badge, theme.soft))
        cur_y += 1

    if err and state == "done":
        runs.append((cur_y, tx_x, ("! " + err)[:tx_w], theme.err))
    elif transcript and state == "done":
        txt_attr = (theme.text if done_tick > 30 else
                    theme.mid  if done_tick > 15 else theme.soft)
        lines     = wrap(transcript[:type_pos], tx_w)
        max_lines = max(1, box_y + box_h - 3 - cur_y)
        for i, line in enumerate(lines[:max_lines]):
            runs.append((cur_y + i, tx_x, line, txt_attr))
        if type_pos < len(transcript) and lines:
            last = lines[min(len(lines) - 1, max_lines - 1)]
            if (tick // 20) % 2 == 0:
                runs.append((cur_y + min(len(lines), max_lines) - 1,
                              tx_x + len(last), "|", theme.on))
    elif state == "idle":
        hint_attr = theme.soft if breathe < 0.4 else theme.label
        runs.append((cur_y, box_x + _cx(box_w, "press SPACE to speak"),
                     "press SPACE to speak", hint_attr))
    elif state == "listening":
        runs.append((cur_y, box_x + _cx(box_w, "SPACE to stop"),
                     "SPACE to stop", theme.label))
    elif state == "processing":
        proc_attr = theme.proc if (tick % 40) < 28 else theme.proc_soft
        if model_was_cold and proc_tick < 180:
            label = "loading model"
        else:
            label = "transcribing"
        runs.append((cur_y, box_x + _cx(box_w, label), label, proc_attr))

    if state == "done" and clipboard_tick > 0:
        cb_attr = theme.done if clipboard_tick > 22 else theme.mid
        runs.append((cur_y + 1, box_x + _cx(box_w, "copied"), "copied", cb_attr))

    if state == "done" and dev_log:
        stat      = dev_log[-1]
        stat_attr = theme.dim if done_tick > 40 else theme.soft
        stat_y    = cur_y + (2 if transcript or err else 0)
        runs.append((stat_y, box_x + _cx(box_w, stat), stat, stat_attr))

    if show_dev and dev_log:
        dy = box_y + box_h - 1 - len(dev_log)
        runs.append((dy, ix + 2, f"{g['H']}{g['H']} DEV " + g["H"] * max(0, iw - 9), theme.label))
        for i, line in enumerate(dev_log):
            runs.append((dy + 1 + i, ix + 4, line[:iw - 6], theme.dim))

    foot_y = box_y + box_h - 2
    if foot_y > cur_y + 2:
        auto_tag = "autocopy on" if auto_copy else "autocopy off"
        kmap = {
            "idle":       [("SPC", "record"), ("M", "model"), ("A", auto_tag), ("H", "dev"), ("Q", "quit")],
            "done":       [("SPC", "again"), ("C", "copy"), ("A", auto_tag), ("↑↓", "hist"), ("ESC", "clear"), ("Q", "quit")],
            "listening":  [("SPC", "stop"),   ("ESC", "cancel"), ("Q", "quit")],
            "processing": [("SPC", "cancel"), ("ESC", "cancel")],
        }
        parts     = [f"{k} {v}" for k, v in kmap.get(state, [])]
        sep       = f"  {g['BULLET']}  "
        foot_attr = theme.dim if state != "idle" else (theme.soft if breathe < 0.4 else theme.dim)
        runs.append((foot_y, box_x + _cx(box_w, sep.join(parts)), sep.join(parts), foot_attr))

    runs.extend(chassis_runs)
    return runs
