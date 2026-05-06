import sys
import io
import numpy as np
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"


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

    lock        = threading.Lock()
    file_done   = {}
    file_total  = {}

    class _ProgressTqdm(_tqdm):
        def update(self, n=1):
            super().update(n)
            if not progress_cb:
                return
            tid = id(self)
            with lock:
                file_done[tid]  = file_done.get(tid, 0) + (n or 0)
                if self.total:
                    file_total[tid] = self.total
                grand_total = sum(file_total.values())
                grand_done  = sum(file_done.values())
            if grand_total > 0:
                progress_cb(min(0.99, grand_done / grand_total))

    import os, sys as _sys
    token = check_token()

    old_stderr = _sys.stderr
    _sys.stderr = open(os.devnull, "w")
    try:
        path = snapshot_download(
            model_id,
            repo_type="model",
            token=token or None,
            tqdm_class=_ProgressTqdm,
        )
    finally:
        _sys.stderr.close()
        _sys.stderr = old_stderr

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


def _transcribe_faster(audio: np.ndarray, model: str) -> tuple[str, str]:
    from faster_whisper import WhisperModel

    short = model.split("/")[-1].replace("faster-whisper-", "")

    if model not in _fw_model_cache:
        try:
            m = WhisperModel(short, device="cuda", compute_type="float16")
            device = "GPU"
        except Exception:
            m = WhisperModel(short, device="cpu", compute_type="int8")
            device = "CPU"
        _fw_model_cache[model] = (m, device)
    else:
        m, device = _fw_model_cache[model]

    segments, _ = m.transcribe(audio.astype(np.float32), beam_size=5)
    return " ".join(s.text for s in segments).strip(), device


def transcribe(audio: np.ndarray, model: str, sample_rate: int) -> tuple[str, str | None]:
    if sys.platform == "darwin":
        return _transcribe_mlx(audio, model), None
    return _transcribe_faster(audio, model)
