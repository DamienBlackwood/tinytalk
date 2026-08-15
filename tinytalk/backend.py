# the new whisper.py OH YEAHH

import io
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import NamedTuple

import numpy as np

BACKEND_NAME = "mlx" if sys.platform == "darwin" else "faster-whisper"

# before it could say that it was downloaded, but now I made it check if the weights are actually present
_WEIGHT_FILES = ("weights.npz", "weights.safetensors", "model.bin")


class Model(NamedTuple):
    repo: str
    label: str
    mb: int


if sys.platform == "darwin":
    MODELS = [
        Model("mlx-community/whisper-tiny",             "TINY",    75),
        Model("mlx-community/whisper-base-mlx",         "BASE",   145),
        Model("mlx-community/whisper-medium-mlx",       "MEDIUM", 1530),
        Model("mlx-community/whisper-large-v3-turbo",   "TURBO",  1620),
    ]
    DEFAULT_MODEL_IDX = 3
else:
    MODELS = [
        Model("Systran/faster-whisper-tiny",       "TINY",     75),
        Model("Systran/faster-whisper-base",       "BASE",    145),
        Model("Systran/faster-whisper-small",      "SMALL",   484),
        Model("Systran/faster-whisper-medium",     "MEDIUM", 1530),
        Model("Systran/faster-whisper-large-v3",   "LARGE",  3090),
    ]
    DEFAULT_MODEL_IDX = 0


def size_label(mb: int) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"


def _cache_root() -> Path:
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        val = os.environ.get(var)
        if val:
            return Path(val).expanduser()
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _hf_snapshot(model_id: str) -> str | None:
    snapshots = _cache_root() / ("models--" + model_id.replace("/", "--")) / "snapshots"
    try:
        revisions = [p for p in snapshots.iterdir() if p.is_dir()]
    except OSError:
        return None
    if not revisions:
        return None
    # newest revision wins, sorting by name would just pick whichever hash happened to start with a low character
    return str(max(revisions, key=lambda p: p.stat().st_mtime))


def is_model_cached(model_id: str) -> bool:
    snapshot = _hf_snapshot(model_id)
    if snapshot is None:
        return False
    folder = Path(snapshot)
    # these are symlinks into blobs/ so a half-finished download reads as missing
    return any((folder / name).exists() for name in _WEIGHT_FILES)


def default_model_idx(fallback: int = DEFAULT_MODEL_IDX) -> int:
    """What to select on a first run. If the usual default isn't on disk but
    something else is, use that instead of making someone sit through a 1.6 GB
    download before they can say hello."""
    if is_model_cached(MODELS[fallback].repo):
        return fallback
    cached = [i for i, m in enumerate(MODELS) if is_model_cached(m.repo)]
    return max(cached, key=lambda i: MODELS[i].mb) if cached else fallback


def check_token() -> str | None:
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:
        return None


def _download_hint(err: Exception) -> str:
    text = str(err)
    name = type(err).__name__
    if any(s in text for s in ("401", "403")) or "gated" in text.lower():
        return "this model needs a login  -  run: hf auth login"
    if any(s in name for s in ("Connection", "Timeout", "DNS", "SSL")):
        return "couldn't reach huggingface  -  check your connection"
    first = text.strip().splitlines()[0] if text.strip() else name
    return f"download failed: {first[:70]}"


def download_model(model_id: str, progress_cb=None) -> str:
    import threading
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as _tqdm

    lock       = threading.Lock()
    file_done  = {}
    file_total = {}

    class _ProgressTqdm(_tqdm):
        def update(self, n=1):
            super().update(n)
            if not progress_cb:
                return
            tid = id(self)
            with lock:
                file_done[tid] = file_done.get(tid, 0) + (n or 0)
                if self.total:
                    file_total[tid] = self.total
                grand_total = sum(file_total.values())
                grand_done  = sum(file_done.values())
            if grand_total > 0:
                progress_cb(min(0.99, grand_done / grand_total))

    # every model is public, so the token is a nice to have for rate limits and nothing more
    sink = io.StringIO()
    try:
        with redirect_stderr(sink):
            path = snapshot_download(
                model_id,
                repo_type="model",
                token=check_token() or None,
                tqdm_class=_ProgressTqdm,
            )
    except Exception as e:
        raise RuntimeError(_download_hint(e)) from e

    if progress_cb:
        progress_cb(1.0)
    return path


def _transcribe_mlx(audio: np.ndarray, model: str) -> str:
    import mlx_whisper

    path = _hf_snapshot(model)
    if path is None:
        raise RuntimeError(f"model not cached: {model}")

    sink = io.StringIO()
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            result = mlx_whisper.transcribe(
                audio.astype(np.float32),
                path_or_hf_repo=path,
                verbose=False,
                # without this whisper feeds its own output back in and can get  stuck repeating a phrase until the clip runs out
                condition_on_previous_text=False,
            )
    except Exception as e:
        detail = sink.getvalue().strip()
        raise RuntimeError(f"{e}" + (f"\n{detail}" if detail else "")) from e

    return result.get("text", "").strip()


_fw_model_cache: dict[str, tuple[object, str]] = {}
_fw_last_key: str | None = None


def _transcribe_faster(audio: np.ndarray, model: str) -> tuple[str, str]:
    global _fw_last_key
    from faster_whisper import WhisperModel

    short = model.split("/")[-1].replace("faster-whisper-", "")

    if model not in _fw_model_cache:
        if _fw_last_key and _fw_last_key != model:
            _fw_model_cache.pop(_fw_last_key, None)

        sink = io.StringIO()
        try:
            with redirect_stdout(sink), redirect_stderr(sink):
                m = WhisperModel(short, device="cuda", compute_type="float16")
            device = "GPU"
        except Exception:
            with redirect_stdout(sink), redirect_stderr(sink):
                m = WhisperModel(short, device="cpu", compute_type="int8")
            device = "CPU"
        _fw_model_cache[model] = (m, device)
        _fw_last_key = model
    else:
        m, device = _fw_model_cache[model]

    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        segments, _ = m.transcribe(
            audio.astype(np.float32),
            beam_size=5,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text for s in segments).strip()

    return text, device


def transcribe(audio: np.ndarray, model: str, sample_rate: int) -> tuple[str, str | None]:
    if sys.platform == "darwin":
        return _transcribe_mlx(audio, model), None
    return _transcribe_faster(audio, model)
