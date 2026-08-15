import json
import time
from typing import Iterator

from . import crypto, paths


def _entry(text: str, model: str, audio_secs: float, words: int) -> dict:
    base = {
        "ts":         time.time(),
        "model":      model,
        "audio_secs": round(audio_secs, 2),
        "words":      words,
    }
    envelope = crypto.encrypt(text)
    if envelope is not None:
        base["text"] = envelope
    else:
        base["text"] = text
    return base


def _resolve_text(field) -> str | None:
    """Text can be a plain string (legacy or fallback) or an envelope dict."""
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        return crypto.decrypt(field)
    return None


def save(text: str, model: str, audio_secs: float, words: int) -> None:
    if not text.strip():
        return
    entry = _entry(text, model, audio_secs, words)
    try:
        paths.ensure_home()
        with paths.TRANSCRIPTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_entries(newest_first: bool = True) -> Iterator[dict]:
    """Every readable entry, with `text` already decrypted. Anything we can't
    make sense of gets skipped rather than blowing up the whole log."""
    try:
        lines = paths.TRANSCRIPTS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in (reversed(lines) if newest_first else lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        text = _resolve_text(entry.get("text"))
        if text is None or not text.strip():
            continue
        yield {**entry, "text": text}


def load_recent(n: int = 5) -> list[str]:
    """The last n transcripts, newest first."""
    out = []
    for entry in read_entries():
        out.append(entry["text"])
        if len(out) >= n:
            break
    return out
