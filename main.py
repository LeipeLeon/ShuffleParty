"""Shuffle Partey — main entry point.

Runs the pygame event loop, coordinating the state machine with
display rendering, audio playback, and hardware I/O.
"""

import sys
import pygame

from shuffle_party import ShuffleParty, State, CONFIG

# Pygame custom events
TIMER_TICK = pygame.USEREVENT + 1
SHUFFLE_TRACK_END = pygame.USEREVENT + 2

# Display constants
BG_COLOR = (0, 0, 0)
TIMER_COLOR = (255, 255, 255)
FONT_SIZE = 200


def run() -> None:
    pygame.init()
    pygame.mixer.init()

    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Shuffle Partey")
    pygame.mouse.set_visible(False)

    clock = pygame.time.Clock()
    font = pygame.font.Font(None, FONT_SIZE)

    # Load shuffle logo if available
    try:
        logo = pygame.image.load("de-shuffle.png")
        logo = pygame.transform.scale(logo, screen.get_size())
    except Exception:
        logo = None

    party = ShuffleParty()

    # Set up the music end event so we detect when shuffle tracks finish
    pygame.mixer.music.set_endevent(SHUFFLE_TRACK_END)

    # Start the 1-second timer tick
    pygame.time.set_timer(TIMER_TICK, 1000)

    # Initial state: DJ set with timer running
    party.display.start_timer()
    party.lighting.activate_dj_set()
    party.mixer.fade_in()

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
                            try:
                                pygame.mixer.music.load(track)
                                pygame.mixer.music.play()
                            except Exception as e:
                                print(f"Warning: Could not play {track} — {e}")

            elif event.type == SHUFFLE_TRACK_END:
                party.on_shuffle_track_ended()

        # Render
        screen.fill(BG_COLOR)

        if party.state == State.DJ_SET:
            time_str = party.display.format_time()
            text = font.render(time_str, True, TIMER_COLOR)
            rect = text.get_rect(center=screen.get_rect().center)
            screen.blit(text, rect)
        elif party.state == State.SHUFFLE:
            if logo:
                screen.blit(logo, (0, 0))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run()
