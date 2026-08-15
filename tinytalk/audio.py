import collections
import math
import shutil
import subprocess
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE  = 16000
CHUNK        = 512
RING_CHUNKS  = 80     # ~2.5s at 16kHz/512

MIN_SECS     = 0.35   # shorter than this and whisper just invents something
SILENCE_PEAK = 0.005  # quieter than this and it invents something anyway


class MicError(RuntimeError):
    pass


def _mic_hint(err: Exception) -> str:
    msg = (str(err).strip() or type(err).__name__).splitlines()[0]
    low = msg.lower()
    if "permission" in low or "denied" in low:
        return "microphone permission denied  -  allow your terminal in system settings"
    if "no default input" in low or "invalid device" in low or "no such device" in low:
        return "no microphone found"
    return f"couldn't open the mic  -  {msg[:60]}"


class AudioCapture:
    def __init__(self, sample_rate=SAMPLE_RATE, chunk=CHUNK):
        self.sample_rate = sample_rate
        self.chunk       = chunk
        self._lock       = threading.Lock()
        self._recording  = False
        self._chunks     = []
        self._ring       = collections.deque(maxlen=RING_CHUNKS)
        self._stream     = None

    def arm(self):
        with self._lock:
            self._chunks.clear()
            self._ring.clear()
        # the stream is opened per recording on purpose.
        if self._stream is None:
            try:
                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    blocksize=self.chunk,
                    dtype="float32",
                    callback=self._cb,
                )
                stream.start()
            except Exception as e:
                raise MicError(_mic_hint(e)) from e
            self._stream = stream
        self._recording = True

    def disarm(self):
        self._recording = False
        with self._lock:
            captured = np.concatenate(self._chunks) if self._chunks else None
            self._chunks.clear()
        self.stop()
        return captured

    def stop(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _cb(self, indata, frames, t, status):
        if not self._recording:
            return
        chunk = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(chunk)
            self._ring.append(chunk)

    def current_rms(self) -> float:
        target = max(self.chunk, self.sample_rate // 60)
        with self._lock:
            if not self._ring:
                return 0.0
            buf, total = [], 0
            for chunk in reversed(self._ring):
                buf.append(chunk)
                total += len(chunk)
                if total >= target:
                    break
            data = np.concatenate(buf[::-1])[-target:]
        if len(data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(data * data)))


def check_clip(audio) -> str | None:
    """The clips that used to make Whisper invent words. None means go ahead."""
    if audio is None or len(audio) == 0:
        return "nothing recorded"
    if len(audio) < SAMPLE_RATE * MIN_SECS:
        return "too short  -  hold space a little longer"
    peak = float(np.abs(audio).max())
    if peak == 0.0:
        return "no audio came through  -  check that your terminal can use the mic"
    if peak < SILENCE_PEAK:
        return "only silence  -  nothing to transcribe"
    return None


def _resample(audio: np.ndarray, src_rate: int) -> np.ndarray:
    if src_rate == SAMPLE_RATE:
        return audio.astype(np.float32, copy=False)
    try:
        from scipy.signal import resample_poly
        g = math.gcd(SAMPLE_RATE, src_rate)
        return resample_poly(audio, SAMPLE_RATE // g, src_rate // g).astype(np.float32)
    except ImportError:
        new_len = int(len(audio) * SAMPLE_RATE / src_rate)
        return np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)), audio,
        ).astype(np.float32)


def _via_ffmpeg(path: Path) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"ffmpeg couldn't read {path.name}"
                           + (f"  -  {detail[-1][:70]}" if detail else ""))
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _via_soundfile(path: Path) -> np.ndarray:
    import soundfile as sf
    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return _resample(audio, rate)


def _via_wave(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise RuntimeError("only 16-bit WAV without ffmpeg, sorry")
        rate    = wf.getframerate()
        raw     = wf.readframes(wf.getnframes())
        audio   = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if wf.getnchannels() == 2:
            audio = audio[: len(audio) // 2 * 2].reshape(-1, 2).mean(axis=1)
    return _resample(audio, rate)


def load_file(path: str) -> np.ndarray:
    """Read any audio file down to mono float32 at 16k. ffmpeg first because it
    reads everything, then soundfile, then the stdlib for plain WAVs."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"no such file: {p}")

    if shutil.which("ffmpeg"):
        audio = _via_ffmpeg(p)
    else:
        try:
            audio = _via_soundfile(p)
        except ImportError:
            if p.suffix.lower() not in (".wav", ".wave"):
                raise RuntimeError(
                    f"install ffmpeg to read {p.suffix.lstrip('.').upper() or 'these'} files"
                ) from None
            audio = _via_wave(p)

    if len(audio) == 0:
        raise RuntimeError(f"{p.name} has no audio in it")
    return audio.astype(np.float32, copy=False)
