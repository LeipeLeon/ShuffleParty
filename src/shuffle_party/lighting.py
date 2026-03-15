"""DMX lighting control for Shuffle Partey.

Drives a pin spot and 4x Showtec LED Par 56 Short via an Enttec DMX USB Pro.

DMX channel map:
  Ch 1:     Pin spot (dimmer)
  Ch 2–7:   Par 1 (R, G, B, Full Color, Strobe, Mode)
  Ch 8–13:  Par 2
  Ch 14–19: Par 3
  Ch 20–25: Par 4

Showtec LED Par 56 Short DMX mode channel (ch 6 per fixture):
  0–63:   RGB manual control
  64–127: 7-color fade
  128–191: 7-color change
  192–255: music-controlled
"""

import logging

from shuffle_party.dmx import DmxOutput

logger = logging.getLogger(__name__)

# DMX addresses (1-indexed)
PIN_SPOT_CH = 1
PAR_ADDRESSES = [2, 8, 14, 20]  # start channel for each par

# Showtec Par 56 channel offsets (relative to start address)
PAR_RED = 0
PAR_GREEN = 1
PAR_BLUE = 2
PAR_FULL_COLOR = 3
PAR_STROBE = 4
PAR_MODE = 5

# Showtec mode values
MODE_RGB = 0
MODE_MUSIC = 255


class Lighting:
    """Controls pin spot and Showtec pars via DMX."""

    def __init__(self, dmx_port: str | None = None) -> None:
        self._dmx = DmxOutput(dmx_port)
        self._target_dj = 1.0
        self._target_shuffle = 0.0

    @property
    def available(self) -> bool:
        return self._dmx.available

    def activate_dj_set(self) -> None:
        """Target: FX pars on (music-reactive), pin spot off."""
        logger.info("Lighting: activate DJ Set")
        self._target_dj = 1.0
        self._target_shuffle = 0.0
        self._apply(self._target_dj, self._target_shuffle)

    def activate_shuffle(self) -> None:
        """Target: FX pars off, pin spot on."""
        logger.info("Lighting: activate Shuffle")
        self._target_dj = 0.0
        self._target_shuffle = 1.0
        self._apply(self._target_dj, self._target_shuffle)

    def update(self, fade_t: float) -> None:
        """Send interpolated values during crossfade (fade_t: 0.0→1.0)."""
        if not self._dmx.available:
            return
        dj_val = self._target_dj * fade_t + (1.0 - self._target_dj) * (1.0 - fade_t)
        shuffle_val = self._target_shuffle * fade_t + (1.0 - self._target_shuffle) * (1.0 - fade_t)
        self._apply(dj_val, shuffle_val)

    def _apply(self, dj_val: float, shuffle_val: float) -> None:
        """Write DMX values and flush."""
        if not self._dmx.available:
            return

        # Pin spot: proportional to shuffle_val
        self._dmx.set_channel(PIN_SPOT_CH, int(shuffle_val * 255))

        # Pars: music-reactive mode at dj_val intensity
        for addr in PAR_ADDRESSES:
            self._dmx.set_channels(addr, [
                0,                        # Red (unused in music mode)
                0,                        # Green
                0,                        # Blue
                0,                        # Full Color
                0,                        # Strobe (off)
                int(dj_val * MODE_MUSIC),  # Mode: 0=off .. 255=music-reactive
            ])

        self._dmx.flush()
        logger.debug("DMX: pin_spot=%d, pars_mode=%d",
                     int(shuffle_val * 255), int(dj_val * MODE_MUSIC))

    def close(self) -> None:
        self._dmx.close()
