"""Shuffle Partey — main entry point.

Runs the pygame event loop with two windows: a display window (logo/timer)
and a control panel. Coordinates the state machine with audio playback
and hardware I/O.
"""

import logging
import os
import sys
import time

import pygame

from shuffle_party import config
from shuffle_party.app import ShuffleParty, State
from shuffle_party.buttons import Buttons
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
            # Start at fadein cue if available
            if control._fadein_cue_ms > 0:
                control._getpos_at_seek_ms = pygame.mixer.music.get_pos()
                control._seek_target_ms = control._fadein_cue_ms
                pygame.mixer.music.set_pos(control._fadein_cue_ms / 1000.0)
        except Exception as e:
            logging.warning(f"Could not play {party.pending_track} — {e!r}")
    party.pending_track = None


def run() -> None:
    pygame.init()
    pygame.mixer.init()

    # Detect displays
    num_displays = pygame.display.get_num_displays()
    multi_display = num_displays >= 2
    primary_size = pygame.display.get_desktop_sizes()[0]
    is_reterminal = primary_size == (1280, 720)

    display_window = None
    if multi_display:
        # Timer fullscreen on external HDMI (display 1)
        display_window = pygame.Window(
            "Shuffle Partey", size=(1920, 1080), display_index=1,
        )
        display_window.set_fullscreen(True)

    clock = pygame.time.Clock()

    # Set macOS dock icon
    try:
        from AppKit import NSApplication, NSImage
        icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "icon.png")
        if not os.path.exists(icon_path):
            icon_path = "icon.png"
        ns_image = NSImage.alloc().initWithContentsOfFile_(os.path.abspath(icon_path))
        if ns_image:
            NSApplication.sharedApplication().setApplicationIconImage_(ns_image)
    except Exception:
        pass

    # Load shuffle logo if available
    try:
        logo_original = pygame.image.load("de-shuffle.png")
    except Exception:
        logo_original = None

    party = ShuffleParty()
    control = ControlPanel(
        party,
        fullscreen=multi_display or is_reterminal,
        display_index=0 if multi_display else None,
    )
    buttons = Buttons(config.BUTTON_DEVICE)

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
    track_played = False

    import signal
    signal.signal(signal.SIGINT, lambda *_: pygame.event.post(pygame.event.Event(pygame.QUIT)))

    running = True
    while running:
        for event in pygame.event.get():
            # Quit
            if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                running = False

            elif (event.type == pygame.KEYDOWN
                  and event.key == pygame.K_f
                  and event.mod & pygame.KMOD_META):
                if party.state == State.IDLE:
                    control._start_dj = True
                else:
                    control._fade_out_now = True

            elif event.type == TIMER_TICK:
                if party.state == State.DJ_SET and not crossfading:
                    expired = party.display.tick()
                    if expired:
                        start_shuffle(party, control)
                        track_played = True

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

        # When mixer crossfade completes back to DJ_SET: stop music, preload
        if was_fading and not party.mixer.is_fading:
            if party.state == State.DJ_SET:
                pygame.mixer.music.stop()
                if track_played:
                    preload_track(party, control)
                    track_played = False

        # Update control panel (fadeout cue check)
        control.update()

        # Poll reTerminal front-panel buttons
        for action in buttons.poll():
            if action == "volume_down":
                control.nudge_volume(-config.VOLUME_STEP)
            elif action == "volume_up":
                control.nudge_volume(config.VOLUME_STEP)
            elif action == "skip_track" and party.state == State.DJ_SET and not crossfading:
                control._skip_track = True
            elif action == "crossfade":
                if party.state == State.DJ_SET:
                    control._fade_out_now = True
                elif party.state == State.IDLE:
                    control._start_dj = True

        # Handle start DJ button (IDLE -> DJ_SET)
        if control.should_start_dj() and party.state == State.IDLE:
            party.start_dj_set()

        # Handle skip track button (load a different track during DJ_SET)
        if control.should_skip_track() and party.state == State.DJ_SET:
            preload_track(party, control)

        # Handle fade out now button
        if control.should_fade_out_now():
            if party.state == State.SHUFFLE:
                party.on_shuffle_track_ended()
            elif party.state == State.DJ_SET:
                start_shuffle(party, control)
                track_played = True

        # Detect state change and start visual crossfade
        if party.state != prev_state:
            crossfade_start = time.monotonic()
            crossfading = True
            prev_state = party.state
            # Reset timer display immediately so it shows full duration during crossfade
            if party.state == State.DJ_SET:
                party.display.remaining_seconds = party.display.set_duration

        # Calculate crossfade progress (0.0 = just started, 1.0 = done)
        if crossfading:
            elapsed = time.monotonic() - crossfade_start
            fade_t = min(1.0, elapsed / CROSSFADE_DURATION)
            if fade_t >= 1.0:
                crossfading = False
                # Start countdown only after visual crossfade into DJ_SET completes
                if party.state == State.DJ_SET:
                    party.display.start_timer()
        else:
            fade_t = 1.0

        control.crossfading = crossfading
        control.fade_t = fade_t

        # Crossfade lighting
        if crossfading:
            party.lighting.update(fade_t)

        # Crossfade the shuffle track audio volume
        if crossfading and pygame.mixer.music.get_busy():
            if party.state == State.SHUFFLE:
                pygame.mixer.music.set_volume(fade_t)
            else:
                pygame.mixer.music.set_volume(1.0 - fade_t)

        # -- Render display window (only if second screen attached) --
        if display_window is not None:
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

    buttons.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run()
