"""Real-time audio analysis for music-reactive lighting.

Captures audio from a USB mixer input, runs FFT each frame, and
exposes frequency band levels (bass, mid, treble) plus beat detection.
Runs in a background thread to avoid blocking the pygame loop.
"""

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

# Analysis parameters
SAMPLE_RATE = 44100
CHUNK_SIZE = 1024  # ~23ms at 44100Hz
CHANNELS = 1

# Frequency band boundaries (Hz)
BASS_LOW = 20
BASS_HIGH = 200
MID_LOW = 200
MID_HIGH = 2000
TREBLE_LOW = 2000
TREBLE_HIGH = 16000

# Beat detection
BEAT_THRESHOLD = 1.6  # ratio of current bass to rolling average
BEAT_HISTORY_SIZE = 40  # ~1 second of history at 30fps read rate


class AudioAnalyzer:
    """Captures audio and provides frequency band levels."""

    def __init__(self, device: int | str | None = None) -> None:
        self._stream = None
        self._running = False
        self._thread: threading.Thread | None = None

        # Current levels (0.0–1.0), updated by the background thread
        self.bass = 0.0
        self.mid = 0.0
        self.treble = 0.0
        self.rms = 0.0
        self.beat = False

        # Beat detection state
        self._bass_history: list[float] = []

        self._device = device
        self._start()

    def _start(self) -> None:
        try:
            import sounddevice as sd

            if self._device is None:
                self._device = self._find_input(sd)

            self._stream = sd.InputStream(
                device=self._device,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                blocksize=CHUNK_SIZE,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("Audio analyzer started (device: %s, %d Hz)",
                        self._device, SAMPLE_RATE)
        except ImportError:
            logger.warning("sounddevice not installed — audio analysis disabled. "
                           "Install with: uv add sounddevice")
        except Exception as e:
            logger.warning(f"Could not open audio input — {e!r}")

    def _find_input(self, sd) -> int | None:  # noqa: ANN001
        """Find a USB audio input device."""
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            name = dev["name"].lower()
            if dev["max_input_channels"] > 0 and (
                "usb" in name or "xr" in name or "behringer" in name or "mixer" in name
            ):
                logger.info("Auto-detected audio input: [%d] %s", i, dev["name"])
                return i
        logger.info("No USB audio input found, using system default")
        return None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,  # noqa: ARG002
        time_info: object,  # noqa: ARG002
        status: object,
    ) -> None:
        """Called by sounddevice for each audio chunk."""
        if status:
            logger.debug("Audio status: %s", status)

        audio = indata[:, 0]  # mono

        # RMS level
        self.rms = min(1.0, float(np.sqrt(np.mean(audio ** 2)) * 4))

        # FFT
        fft = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / SAMPLE_RATE)

        # Band levels (normalized)
        self.bass = self._band_level(fft, freqs, BASS_LOW, BASS_HIGH)
        self.mid = self._band_level(fft, freqs, MID_LOW, MID_HIGH)
        self.treble = self._band_level(fft, freqs, TREBLE_LOW, TREBLE_HIGH)

        # Beat detection: compare current bass to rolling average
        self._bass_history.append(self.bass)
        if len(self._bass_history) > BEAT_HISTORY_SIZE:
            self._bass_history.pop(0)
        avg_bass = sum(self._bass_history) / len(self._bass_history) if self._bass_history else 0
        self.beat = self.bass > avg_bass * BEAT_THRESHOLD and self.bass > 0.15

    def _band_level(
        self, fft: np.ndarray, freqs: np.ndarray, low: float, high: float,
    ) -> float:
        """Average FFT magnitude in a frequency band, normalized to 0.0–1.0."""
        mask = (freqs >= low) & (freqs <= high)
        if not np.any(mask):
            return 0.0
        level = float(np.mean(fft[mask]))
        # Normalize: typical music FFT magnitudes are 0–~50 for float32 input
        return min(1.0, level / 12.0)

    @property
    def available(self) -> bool:
        return self._stream is not None

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
