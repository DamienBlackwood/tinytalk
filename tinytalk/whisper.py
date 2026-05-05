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


def _transcribe_mlx(audio: np.ndarray, model: str) -> str:
    import mlx_whisper

    path = _hf_snapshot(model)
    if path is None:
        raise RuntimeError(f"model not installed, run: hf download {model}")

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

_status_callback = None


def set_status_callback(fn):
    global _status_callback
    _status_callback = fn


def ensure_model_downloaded(model: str):
    if is_model_cached(model):
        return
    from faster_whisper import WhisperModel
    short = model.split("/")[-1].replace("faster-whisper-", "")
    print(f"downloading {short} model — this only happens once")
    try:
        WhisperModel(short, device="cuda", compute_type="float16")
    except Exception:
        WhisperModel(short, device="cpu", compute_type="int8")
    print("done.\n")


_model_cache: dict[str, tuple[object, str]] = {}


def _transcribe_faster(audio: np.ndarray, model: str) -> tuple[str, str]:
    from faster_whisper import WhisperModel

    short = model.split("/")[-1].replace("faster-whisper-", "")

    if model not in _model_cache:
        if not is_model_cached(model) and _status_callback:
            _status_callback("downloading")

        try:
            try:
                m = WhisperModel(short, device="cuda", compute_type="float16")
                device = "GPU"
            except Exception:
                m = WhisperModel(short, device="cpu", compute_type="int8")
                device = "CPU"
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                raise RuntimeError(
                    "HuggingFace rate limited — run: hf login"
                ) from e
            raise

        _model_cache[model] = (m, device)

        if _status_callback:
            _status_callback("loaded")
    else:
        m, device = _model_cache[model]
        if _status_callback:
            _status_callback("loaded")

    segments, _ = m.transcribe(audio.astype(np.float32), beam_size=5)
    return " ".join(s.text for s in segments).strip(), device


def transcribe(audio: np.ndarray, model: str, sample_rate: int) -> tuple[str, str | None]:
    if sys.platform == "darwin":
        return _transcribe_mlx(audio, model), None
    return _transcribe_faster(audio, model)
