"""Shuffle Partey — main entry point.

Runs the pygame event loop, coordinating the state machine with
display rendering, audio playback, and hardware I/O.
"""

import logging
import sys
import time
import pygame

from shuffle_party.app import ShuffleParty, State
from shuffle_party import config
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


def run() -> None:
    pygame.init()
    pygame.mixer.init()

    screen = pygame.display.set_mode((800, 300), pygame.RESIZABLE)
    pygame.display.set_caption("Shuffle Partey")

    clock = pygame.time.Clock()

    # Load shuffle logo if available
    try:
        logo_original = pygame.image.load("de-shuffle.png")
    except Exception:
        logo_original = None

    party = ShuffleParty()

    # Launch control panel in a separate process
    control = ControlPanel(party)

    # Set up the music end event so we detect when shuffle tracks finish
    pygame.mixer.music.set_endevent(SHUFFLE_TRACK_END)

    # Start the 1-second timer tick
    pygame.time.set_timer(TIMER_TICK, 1000)

    # Initial state: DJ set with timer running
    party.display.start_timer()
    party.lighting.activate_dj_set()
    party.mixer.fade_in()

    # Crossfade state
    prev_state = party.state
    crossfade_start = 0.0  # timestamp when transition began
    crossfading = False

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            elif event.type == TIMER_TICK:
                if party.state == State.DJ_SET:
                    expired = party.display.tick()
                    if expired:
                        track = party.on_timer_expired()
                        if track:
                            control.set_track_name(track)
                            try:
                                pygame.mixer.music.load(track)
                                pygame.mixer.music.set_volume(0.0)
                                pygame.mixer.music.play()
                            except Exception as e:
                                print(f"Warning: Could not play {track} — {e}")

            elif event.type == SHUFFLE_TRACK_END:
                control.set_track_name("")
                party.on_shuffle_track_ended()

        # Sync shared state with control panel
        control.update()

        # Handle fade out now button
        if control.should_fade_out_now():
            if party.state == State.SHUFFLE:
                pygame.mixer.music.fadeout(int(party.mixer.fade_duration * 1000))
            elif party.state == State.DJ_SET:
                track = party.on_timer_expired()
                if track:
                    control.set_track_name(track)
                    try:
                        pygame.mixer.music.load(track)
                        pygame.mixer.music.set_volume(0.0)
                        pygame.mixer.music.play()
                    except Exception as e:
                        print(f"Warning: Could not play {track} — {e}")

        # Detect state change and start crossfade
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

        # Crossfade the shuffle track audio volume
        if crossfading and pygame.mixer.music.get_busy():
            if party.state == State.SHUFFLE:
                pygame.mixer.music.set_volume(fade_t)
            else:
                pygame.mixer.music.set_volume(1.0 - fade_t)

        # Render with crossfade
        screen.fill(BG_COLOR)
        w, h = screen.get_size()

        # Determine alpha for each layer
        if party.state == State.SHUFFLE:
            timer_alpha = int(255 * (1.0 - fade_t))
            logo_alpha = int(255 * fade_t)
        else:
            timer_alpha = int(255 * fade_t)
            logo_alpha = int(255 * (1.0 - fade_t))

        # Draw logo layer
        if logo_original and logo_alpha > 0:
            logo = pygame.transform.scale(logo_original, (w, h))
            logo.set_alpha(logo_alpha)
            screen.blit(logo, (0, 0))

        # Draw timer layer
        if timer_alpha > 0:
            font = pygame.font.Font(None, int(h * 0.7))
            time_str = party.display.format_time()
            text_surface = font.render(time_str, True, TIMER_COLOR)
            text_surface.set_alpha(timer_alpha)
            rect = text_surface.get_rect(center=(w // 2, h // 2))
            screen.blit(text_surface, rect)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run()
