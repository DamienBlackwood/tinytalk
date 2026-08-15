import threading
import collections
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
