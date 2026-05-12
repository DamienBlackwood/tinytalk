import json
import time
from pathlib import Path

from . import crypto

_LOG_PATH = Path(__file__).parent.parent / ".tinytalk" / "transcripts.jsonl"


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
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load_recent(n: int = 5) -> list[str]:
    """Return the last n transcript texts, the newest ones being first. Skips undecryptable
    entries silently"""
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    texts = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = _resolve_text(entry.get("text"))
        if text and text.strip():
            texts.append(text)
            if len(texts) >= n:
                break
    return texts
