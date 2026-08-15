"""
`tinytalk log` - read back what you've said.

The transcripts are encrypted with the key sitting next to them, so this only
works on the machine that recorded them. Anything it can't decrypt gets counted
and skipped rather than printed as noise.
"""
import argparse
import sys
import time
from pathlib import Path

from . import paths, transcripts

_ANSI = {
    "dim":   "\033[38;5;243m",
    "label": "\033[38;5;246m",
    "hot":   "\033[38;5;214m",
    "good":  "\033[38;5;79m",
    "off":   "\033[0m",
}


def _paint(enabled):
    if enabled:
        return lambda name, text: f"{_ANSI[name]}{text}{_ANSI['off']}"
    return lambda name, text: text


def _ago(ts: float) -> str:
    secs = max(0, time.time() - ts)
    if secs < 90:
        return "just now"
    mins = secs / 60
    if mins < 60:
        return f"{int(mins)}m ago"
    hours = mins / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    days = hours / 24
    if days < 14:
        return f"{int(days)}d ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def _is_today(ts: float) -> bool:
    return time.strftime("%Y-%m-%d", time.localtime(ts)) == time.strftime("%Y-%m-%d")


def _one_line(text: str, width: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1].rstrip() + "…"


def _collect(args):
    out = []
    for entry in transcripts.read_entries():
        ts = entry.get("ts", 0)
        if args.today and not _is_today(ts):
            continue
        if args.search and args.search.lower() not in entry["text"].lower():
            continue
        out.append(entry)
        if not args.all and len(out) >= args.number:
            break
    return out


def _export(entries, target: Path, force: bool) -> int:
    if target.exists() and not force:
        print(f"{target} already exists. pass --force to overwrite it.", file=sys.stderr)
        return 1
    body = []
    for e in entries:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("ts", 0)))
        body.append(f"[{stamp}] {e.get('model', '?')}\n{e['text']}\n")
    try:
        target.write_text("\n".join(body), encoding="utf-8")
    except OSError as e:
        print(f"couldn't write {target}: {e}", file=sys.stderr)
        return 1
    print(f"wrote {len(entries)} transcripts to {target}")
    print("heads up: that file is plain text, unlike the log it came from.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tinytalk log",
        description="read back your transcripts",
    )
    p.add_argument("-n", "--number", type=int, default=20, metavar="N",
                   help="how many to show (default 20)")
    p.add_argument("--all", action="store_true", help="show everything")
    p.add_argument("--today", action="store_true", help="only today's")
    p.add_argument("--search", metavar="TEXT", help="only ones containing TEXT")
    p.add_argument("--full", action="store_true", help="print whole transcripts, not previews")
    p.add_argument("--export", metavar="FILE", help="dump them to a plain text file")
    p.add_argument("--force", action="store_true", help="let --export overwrite")
    args = p.parse_args(argv)

    if not paths.TRANSCRIPTS.exists():
        print(f"no transcripts yet. they'll show up in {paths.TRANSCRIPTS}")
        return 0

    entries = _collect(args)

    if args.export:
        if not entries:
            print("nothing to export.")
            return 0
        return _export(entries, Path(args.export).expanduser(), args.force)

    if not entries:
        print("nothing matched." if (args.search or args.today) else "nothing in the log yet.")
        return 0

    paint = _paint(sys.stdout.isatty())
    width = 78

    for e in entries:
        words = e.get("words", len(e["text"].split()))
        meta = "  ".join([
            f"{_ago(e.get('ts', 0)):>12}",
            f"{e.get('model', '?'):<7}",
            f"{e.get('audio_secs', 0):>5.1f}s",
            f"{words:>4} {'word' if words == 1 else 'words'}",
        ])
        print(paint("label", meta))
        if args.full:
            print(f"  {e['text']}\n")
        else:
            print("  " + paint("dim", _one_line(e["text"], width)) + "\n")

    total = len(entries)
    secs  = sum(e.get("audio_secs", 0) for e in entries)
    words = sum(e.get("words", 0) for e in entries)
    print(paint("dim", f"{total} transcripts  ·  {secs / 60:.1f} min of audio  ·  {words} words"))
    return 0
