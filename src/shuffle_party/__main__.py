"""Shuffle Partey — main entry point.

Runs the pygame event loop with two windows: a display window (logo/timer)
and a control panel. Coordinates the state machine with audio playback
and hardware I/O.
"""

import logging
import sys
import time

import pygame

from shuffle_party import config
from shuffle_party.app import ShuffleParty, State
from shuffle_party.control_panel import ControlPanel

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

# Pygame custom events
TIMER_TICK = pygame.USEREVENT + 1
SHUFFLE_TRACK_END = pygame.USEREVENT + 2

# Display constants
BG_COLOR = (0, 0, 0)
TIMER_COLOR = (255, 255, 255)
CROSSFADE_DURATION = config.CROSSFADE_DURATION_SECONDS


def preload_track(party, control) -> None:
    """Pick the next track, load it into pygame, and show it on the control panel."""
    track = party.track_picker.pick()
    party.pending_track = track
    if track:
        control.set_track_name(track)
        try:
            pygame.mixer.music.load(track)
            pygame.mixer.music.set_volume(0.0)
        except Exception as e:
            logging.warning(f"Could not pre-load {track} — {e!r}")
            party.pending_track = None


def start_shuffle(party, control) -> None:
    """Begin the shuffle transition, playing the pre-loaded track."""
    party.on_timer_expired()
    if party.pending_track:
        try:
            pygame.mixer.music.play()
        except Exception as e:
            logging.warning(f"Could not play {party.pending_track} — {e!r}")
    party.pending_track = None


def run() -> None:
    pygame.init()
    pygame.mixer.init()

    # Create both windows
    display_window = pygame.Window(
        "Shuffle Partey", size=(270, 180), resizable=True,
    )

    clock = pygame.time.Clock()

    # Load shuffle logo if available
    try:
        logo_original = pygame.image.load("de-shuffle.png")
    except Exception:
        logo_original = None

    party = ShuffleParty()
    control = ControlPanel(party)

    # Set up the music end event so we detect when shuffle tracks finish
    pygame.mixer.music.set_endevent(SHUFFLE_TRACK_END)

    # Start the 1-second timer tick
    pygame.time.set_timer(TIMER_TICK, 1000)

    # Pre-load the first shuffle track
    preload_track(party, control)

    # Start in IDLE — show logo, wait for "Start DJ Set" button

    # Crossfade state
    prev_state = party.state
    crossfade_start = 0.0
    crossfading = False

    import signal
    signal.signal(signal.SIGINT, lambda *_: pygame.event.post(pygame.event.Event(pygame.QUIT)))

    running = True
    while running:
        for event in pygame.event.get():
            # Quit
            if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                running = False

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            elif event.type == TIMER_TICK:
                if party.state == State.DJ_SET:
                    expired = party.display.tick()
                    if expired:
                        start_shuffle(party, control)

            elif event.type == SHUFFLE_TRACK_END:
                if party.state == State.SHUFFLE:
                    party.on_shuffle_track_ended()

            # Route mouse/keyboard events to control panel window
            elif (hasattr(event, "window")
                  and event.window == control.window):
                control.handle_event(event)

        # Advance mixer crossfade
        was_fading = party.mixer.is_fading
        party.mixer.tick()

        # When crossfade back to DJ_SET completes: stop music, preload next
        if was_fading and not party.mixer.is_fading and party.state == State.DJ_SET:
            pygame.mixer.music.stop()
            preload_track(party, control)

        # Update control panel (fadeout cue check)
        control.update()

        # Handle start DJ button (IDLE -> DJ_SET)
        if control.should_start_dj() and party.state == State.IDLE:
            party.start_dj_set()

        # Handle fade out now button
        if control.should_fade_out_now():
            if party.state == State.SHUFFLE:
                party.on_shuffle_track_ended()
            elif party.state == State.DJ_SET:
                start_shuffle(party, control)

        # Detect state change and start visual crossfade
        if party.state != prev_state:
            crossfade_start = time.monotonic()
            crossfading = True
            prev_state = party.state

        # Calculate crossfade progress (0.0 = just started, 1.0 = done)
        if crossfading:
            elapsed = time.monotonic() - crossfade_start
            fade_t = min(1.0, elapsed / CROSSFADE_DURATION)
            if fade_t >= 1.0:
                crossfading = False
        else:
            fade_t = 1.0

        # Crossfade lighting
        if crossfading:
            party.lighting.update(fade_t)

        # Crossfade the shuffle track audio volume
        if crossfading and pygame.mixer.music.get_busy():
            if party.state == State.SHUFFLE:
                pygame.mixer.music.set_volume(fade_t)
            else:
                pygame.mixer.music.set_volume(1.0 - fade_t)

        # -- Render display window --
        screen = display_window.get_surface()
        screen.fill(BG_COLOR)
        w, h = screen.get_size()

        # Determine alpha for each layer
        if party.state == State.IDLE:
            timer_alpha = 0
            logo_alpha = 255
        elif party.state == State.SHUFFLE:
            timer_alpha = int(255 * (1.0 - fade_t))
            logo_alpha = int(255 * fade_t)
        else:
            timer_alpha = int(255 * fade_t)
            logo_alpha = int(255 * (1.0 - fade_t))

        # Draw logo layer (fit to window, preserving aspect ratio)
        if logo_original and logo_alpha > 0:
            orig_w, orig_h = logo_original.get_size()
            scale = min(w / orig_w, h / orig_h)
            logo_w = int(orig_w * scale)
            logo_h = int(orig_h * scale)
            logo = pygame.transform.smoothscale(logo_original, (logo_w, logo_h))
            logo.set_alpha(logo_alpha)
            logo_x = (w - logo_w) // 2
            logo_y = (h - logo_h) // 2
            screen.blit(logo, (logo_x, logo_y))

        # Draw timer layer
        if timer_alpha > 0:
            font = pygame.font.Font(None, int(h * 0.7))
            time_str = party.display.format_time()
            text_surface = font.render(time_str, True, TIMER_COLOR)
            text_surface.set_alpha(timer_alpha)
            rect = text_surface.get_rect(center=(w // 2, h // 2))
            screen.blit(text_surface, rect)

        display_window.flip()

        # -- Render control panel --
        control.draw()

        clock.tick(30)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run()
