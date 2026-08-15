# the new whisper.py OH YEAHH

import sys
import io
import numpy as np
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import NamedTuple

_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"

BACKEND_NAME = "mlx" if sys.platform == "darwin" else "faster-whisper"


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


def _hf_snapshot(model_id: str) -> str | None:
    folder    = _HF_CACHE / ("models--" + model_id.replace("/", "--"))
    snapshots = folder / "snapshots"
    if not snapshots.exists():
        return None
    entries = sorted(snapshots.iterdir())
    return str(entries[0]) if entries else None


def is_model_cached(model_id: str) -> bool:
    return _hf_snapshot(model_id) is not None


def check_token() -> str | None:
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:
        return None


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

    import os
    token = check_token()

    old_stderr = sys.stderr
    sys.stderr = open(os.devnull, "w")
    try:
        path = snapshot_download(
            model_id,
            repo_type="model",
            token=token or None,
            tqdm_class=_ProgressTqdm,
        )
    finally:
        sys.stderr.close()
        sys.stderr = old_stderr

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
        segments, _ = m.transcribe(audio.astype(np.float32), beam_size=5)
        text = " ".join(s.text for s in segments).strip()

    return text, device


def transcribe(audio: np.ndarray, model: str, sample_rate: int) -> tuple[str, str | None]:
    if sys.platform == "darwin":
        return _transcribe_mlx(audio, model), None
    return _transcribe_faster(audio, model)
