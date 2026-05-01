import sys
import os
import numpy as np
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

    devnull  = open(os.devnull, "w")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = devnull
    try:
        result = mlx_whisper.transcribe(
            audio.astype(np.float32),
            path_or_hf_repo=path,
            verbose=False,
        )
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        devnull.close()

    return result.get("text", "").strip()
