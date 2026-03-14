"""reTerminal front-panel button support via evdev.

The Seeed Studio reTerminal exposes F1/F2/F3 and the circular "O" button
as standard Linux input events. This module provides non-blocking polling
for use inside a pygame event loop.
"""

import logging
import platform

logger = logging.getLogger(__name__)

# Key codes for the reTerminal buttons
_KEY_F1 = 59
_KEY_F2 = 60
_KEY_F3 = 61

# The "O" button is typically mapped as KEY_ENTER (28)
_KEY_O = 28


class Buttons:
    """Non-blocking reader for reTerminal front-panel buttons."""

    def __init__(self, device_path: str = "/dev/input/event0") -> None:
        self._device = None
        self._available = False

        if platform.system() != "Linux":
            logger.info("Not on Linux — reTerminal buttons disabled.")
            return

        try:
            from evdev import InputDevice
            self._device = InputDevice(device_path)
            self._device.grab()  # exclusive access so keys don't echo
            self._available = True
            logger.info("reTerminal buttons active on %s (%s)", device_path, self._device.name)
        except ImportError:
            logger.info("evdev not installed — reTerminal buttons disabled.")
        except Exception as e:
            logger.warning("Could not open %s — %r", device_path, e)

    @property
    def available(self) -> bool:
        return self._available

    def poll(self) -> list[str]:
        """Return a list of button actions that occurred since last poll.

        Possible values: "volume_down", "volume_up", "skip_track", "crossfade".
        Only key-down events are returned (not repeats or releases).
        """
        if not self._available or self._device is None:
            return []

        actions: list[str] = []
        try:
            from evdev import ecodes
            for event in self._device.read():
                if event.type != ecodes.EV_KEY:
                    continue
                # value 1 = key down, 0 = key up, 2 = repeat
                if event.value != 1:
                    continue
                if event.code == _KEY_F1:
                    actions.append("volume_down")
                elif event.code == _KEY_F2:
                    actions.append("volume_up")
                elif event.code == _KEY_F3:
                    actions.append("skip_track")
                elif event.code == _KEY_O:
                    actions.append("crossfade")
        except BlockingIOError:
            pass  # no events available
        except Exception as e:
            logger.warning("Error reading buttons: %r", e)

        return actions

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.ungrab()
            except Exception:
                pass
            self._device.close()
            self._device = None
            self._available = False
