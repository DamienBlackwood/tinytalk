import threading
import collections
import numpy as np
import sounddevice as sd

SAMPLE_RATE  = 16000
CHUNK        = 512
# keep ~2.5s of recent chunks — enough for 120 bars at any terminal width
RING_CHUNKS  = 80


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
        self._recording = True
        if self._stream is None:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.chunk,
                dtype="float32",
                callback=self._cb,
            )
            self._stream.start()

    def disarm(self):
        self._recording = False
        with self._lock:
            captured = (
                np.concatenate(self._chunks)
                if self._chunks
                else np.zeros(self.sample_rate // 4, dtype=np.float32)
            )
            self._chunks.clear()
        self.stop()
        return captured

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _cb(self, indata, frames, t, status):
        if not self._recording:
            return
        chunk = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(chunk)
            self._ring.append(chunk)

    def current_rms(self) -> float:
        """
        RMS of the most recent ~1 frame of audio (~16ms at 60fps). The app
        feeds this into a scrolling history so each frame produces exactly
        one new bar and no re-pooling, no jitter.
        """
        # ~16ms at 16kHz = 256 samples. Round up to chunk boundary.
        target = max(self.chunk, self.sample_rate // 60)
        with self._lock:
            if not self._ring:
                return 0.0
            # walk newest-first until we have enough
            buf = []
            total = 0
            for chunk in reversed(self._ring):
                buf.append(chunk)
                total += len(chunk)
                if total >= target:
                    break
            data = np.concatenate(buf[::-1])[-target:]
        if len(data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(data * data)))
