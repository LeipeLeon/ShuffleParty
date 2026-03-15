"""DMX lighting control for Shuffle Partey.

Drives a pin spot and 4x Showtec LED Par 56 Short via an Enttec DMX USB Pro.
During DJ sets, pars react to live audio (bass→red, mid→green, treble→blue).
During shuffle, pin spot on, pars off.

DMX channel map:
  Ch 1:     Pin spot (dimmer)
  Ch 2–7:   Par 1 (R, G, B, Full Color, Strobe, Mode)
  Ch 8–13:  Par 2
  Ch 14–19: Par 3
  Ch 20–25: Par 4

Showtec LED Par 56 Short DMX — Mode 1 (ch 6 = 0–63): RGB manual control.
"""

import logging

from shuffle_party.audio_analyzer import AudioAnalyzer
from shuffle_party.dmx import DmxOutput

logger = logging.getLogger(__name__)

# DMX addresses (1-indexed)
PIN_SPOT_CH = 1
PAR_ADDRESSES = [2, 8, 14, 20]

# Showtec Par 56 channel offsets
PAR_RED = 0
PAR_GREEN = 1
PAR_BLUE = 2
PAR_FULL_COLOR = 3
PAR_STROBE = 4
PAR_MODE = 5

# RGB manual control mode
MODE_RGB = 0

# Minimum brightness so lights aren't completely off between beats
MIN_BRIGHTNESS = 30
# Beat flash boost
BEAT_BOOST = 80


class Lighting:
    """Controls pin spot and Showtec pars via DMX with audio-reactive effects."""

    def __init__(
        self,
        dmx_port: str | None = None,
        audio_device: int | str | None = None,
    ) -> None:
        self._dmx = DmxOutput(dmx_port)
        self._audio = AudioAnalyzer(audio_device)
        self._target_dj = 1.0
        self._target_shuffle = 0.0
        self._dj_intensity = 1.0

    @property
    def available(self) -> bool:
        return self._dmx.available

    def activate_dj_set(self) -> None:
        """Target: audio-reactive pars on, pin spot off."""
        logger.info("Lighting: activate DJ Set")
        self._target_dj = 1.0
        self._target_shuffle = 0.0

    def activate_shuffle(self) -> None:
        """Target: pars off, pin spot on."""
        logger.info("Lighting: activate Shuffle")
        self._target_dj = 0.0
        self._target_shuffle = 1.0

    def update(self, fade_t: float) -> None:
        """Called each frame. During crossfade, interpolates. Otherwise drives audio-reactive."""
        if not self._dmx.available:
            return
        dj_val = self._target_dj * fade_t + (1.0 - self._target_dj) * (1.0 - fade_t)
        shuffle_val = self._target_shuffle * fade_t + (1.0 - self._target_shuffle) * (1.0 - fade_t)
        self._dj_intensity = dj_val
        self._apply(dj_val, shuffle_val)

    def tick(self) -> None:
        """Called each frame (not during crossfade). Drives audio-reactive lighting."""
        if not self._dmx.available:
            return
        self._apply(self._dj_intensity, 1.0 - self._dj_intensity)

    def _apply(self, dj_val: float, shuffle_val: float) -> None:
        """Write DMX values based on audio analysis and state."""
        if not self._dmx.available:
            return

        # Pin spot: proportional to shuffle intensity
        self._dmx.set_channel(PIN_SPOT_CH, int(shuffle_val * 255))

        # Pars: audio-reactive RGB during DJ set
        if dj_val > 0 and self._audio.available:
            bass = self._audio.bass
            mid = self._audio.mid
            treble = self._audio.treble
            beat = self._audio.beat

            # Map frequency bands to RGB
            r = int((bass * 200 + MIN_BRIGHTNESS) * dj_val)
            g = int((mid * 180 + MIN_BRIGHTNESS * 0.5) * dj_val)
            b = int((treble * 160 + MIN_BRIGHTNESS * 0.3) * dj_val)

            # Beat flash: boost all channels on kick
            if beat:
                r = min(255, r + BEAT_BOOST)
                g = min(255, g + int(BEAT_BOOST * 0.3))
                b = min(255, b + int(BEAT_BOOST * 0.2))

            r = min(255, r)
            g = min(255, g)
            b = min(255, b)

            for addr in PAR_ADDRESSES:
                self._dmx.set_channels(addr, [r, g, b, 0, 0, MODE_RGB])
        else:
            # No audio or DJ off: pars dark
            for addr in PAR_ADDRESSES:
                self._dmx.set_channels(addr, [0, 0, 0, 0, 0, MODE_RGB])

        self._dmx.flush()

    def close(self) -> None:
        self._audio.close()
        self._dmx.close()
