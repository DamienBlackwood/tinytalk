import sys
import io
import numpy as np
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"


def _local_path(model_id: str) -> str | None:
    folder    = _HF_CACHE / ("models--" + model_id.replace("/", "--"))
    snapshots = folder / "snapshots"
    if not snapshots.exists():
        return None
    entries = sorted(snapshots.iterdir())
    return str(entries[0]) if entries else None


def transcribe(audio: np.ndarray, model: str, sample_rate: int) -> str:
    import mlx_whisper

    path = _local_path(model)
    if path is None:
        raise RuntimeError(f"model not installed — run: huggingface-cli download {model}")

    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        result = mlx_whisper.transcribe(
            audio.astype(np.float32),
            path_or_hf_repo=path,
            verbose=False,
        )

    return result.get("text", "").strip()
