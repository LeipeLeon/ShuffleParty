"""Shuffle Partey — main entry point.

Runs the pygame event loop with two windows: a display window (logo/timer)
and a control panel. Coordinates the state machine with audio playback
and hardware I/O.
"""

import logging
import os
import signal
import sys
import time

import pygame

from shuffle_party import config
from shuffle_party.app import ShuffleParty, State
from shuffle_party.buttons import Buttons
from shuffle_party.control_panel import ControlPanel
from shuffle_party.loudness import db_to_fader, fader_for_target, measure_lufs
from shuffle_party.midi_controller import MidiExtender, build_channel_map

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
        lufs = measure_lufs(track)
        fader_pos = fader_for_target(lufs) if lufs is not None else db_to_fader(0)
        if lufs is not None:
            logging.info("Track %.1f LUFS → fader %.3f: %s", lufs, fader_pos, os.path.basename(track))
        control.set_track_gain(fader_pos, lufs)
        party.mixer.shuffle_gain = fader_pos
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
            # Seek to the playhead position (set by user or fadein cue)
            if control._seek_target_ms > 0:
                control._getpos_at_seek_ms = pygame.mixer.music.get_pos()
                pygame.mixer.music.set_pos(control._seek_target_ms / 1000.0)
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
    is_reterminal = primary_size in ((1280, 720), (1280, 800))

    display_window = None
    if multi_display:
        # Timer fullscreen on external HDMI (display 1)
        # Position on second display by offsetting past the primary display width
        display_window = pygame.Window(
            "Shuffle Partey", size=pygame.display.get_desktop_sizes()[1],
        )
        display_window.position = (pygame.display.get_desktop_sizes()[0][0], 0)
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

    # Cached display font (created on first use / resize)
    display_font = None
    display_font_size = 0

    # Load shuffle logo if available
    try:
        logo_original = pygame.image.load("de-shuffle.png")
    except Exception:
        logo_original = None
    logo_scaled = None
    logo_scaled_size = (0, 0)

    party = ShuffleParty()
    control = ControlPanel(
        party,
        fullscreen=multi_display or is_reterminal,
        volume_step=config.VOLUME_STEP,
    )
    buttons = Buttons(config.BUTTON_DEVICE)
    channel_map = build_channel_map(
        dj_channels=[config.DJ_CHANNEL_L, config.DJ_CHANNEL_R],
        shuffle_channels=[config.SHUFFLE_CHANNEL_L, config.SHUFFLE_CHANNEL_R],
    )
    extender = MidiExtender(
        config.MIDI_EXTENDER_PORT, channel_map,
        network_host=config.MIDI_EXTENDER_HOST,
    )

    # Sync extender faders with current XR12 state
    if extender.available:
        all_channels = [ch for group in channel_map for ch in group]
        xr12_levels = party.mixer.query_channel_faders(all_channels)
        for fader_idx, channels in enumerate(channel_map):
            if channels[0] in xr12_levels:
                extender.set_fader(fader_idx, xr12_levels[channels[0]])
        master = party.mixer.query_master_fader()
        if master is not None:
            extender.set_master_fader(master)
            control.set_volume(master)

    # Set XR12 volume channels to initial state (DJ at 0 dB, shuffle off)
    party.mixer.set_channel_volume(party.mixer.dj_channels, party.mixer.dj_target)
    party.mixer.set_channel_volume(party.mixer.shuffle_channels, 0.0)

    # Start web-based remote display if enabled
    web_display = None
    if config.WEB_DISPLAY_ENABLED:
        from shuffle_party.web_display import WebDisplay

        logo_path = os.path.abspath("de-shuffle.png")
        web_display = WebDisplay(config.WEB_DISPLAY_PORT, logo_path)
        web_display.start()

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

        # Poll X-TOUCH EXTENDER faders (channels 1–7 + master on fader 8)
        channel_changes, master_value = extender.poll()
        for fader_idx, value in channel_changes.items():
            channels = extender.channel_map[fader_idx]
            party.mixer.set_channel_volume(channels, value)
        if master_value is not None:
            control.set_volume(master_value)
        if extender.available:
            # Sync motorized faders with crossfade state
            dj_idx = extender.fader_index_for_channels(party.mixer.dj_channels)
            if dj_idx is not None:
                extender.set_fader(dj_idx, party.mixer.dj_level)
            sh_idx = extender.fader_index_for_channels(party.mixer.shuffle_channels)
            if sh_idx is not None:
                extender.set_fader(sh_idx, party.mixer.shuffle_level)
            # Sync master fader
            extender.set_master_fader(control._volume_value)

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

        # Handle reset to IDLE
        if control.should_reset():
            pygame.mixer.music.stop()
            party.reset()
            crossfading = False
            fade_t = 1.0
            track_played = False
            preload_track(party, control)

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

        # Update lighting: crossfade or audio-reactive
        if crossfading:
            party.lighting.update(fade_t)
        else:
            party.lighting.tick()

        # Crossfade the shuffle track audio volume
        if crossfading and pygame.mixer.music.get_busy():
            if party.state == State.SHUFFLE:
                pygame.mixer.music.set_volume(fade_t)
            else:
                pygame.mixer.music.set_volume(1.0 - fade_t)

        # Determine alpha for each layer (used by both pygame and web display)
        if party.state == State.IDLE:
            timer_alpha = 0
            logo_alpha = 255
        elif party.state == State.SHUFFLE:
            timer_alpha = int(255 * (1.0 - fade_t))
            logo_alpha = int(255 * fade_t)
        else:
            timer_alpha = int(255 * fade_t)
            logo_alpha = int(255 * (1.0 - fade_t))

        # -- Render display window (only if second screen attached) --
        if display_window is not None:
            screen = display_window.get_surface()
            screen.fill(BG_COLOR)
            w, h = screen.get_size()

            # Draw logo layer (fit to window, preserving aspect ratio)
            if logo_original and logo_alpha > 0:
                orig_w, orig_h = logo_original.get_size()
                scale = min(w / orig_w, h / orig_h)
                logo_w = int(orig_w * scale)
                logo_h = int(orig_h * scale)
                target_size = (logo_w, logo_h)
                if logo_scaled is None or logo_scaled_size != target_size:
                    logo_scaled = pygame.transform.smoothscale(logo_original, target_size)
                    logo_scaled_size = target_size
                logo = logo_scaled.copy()
                logo.set_alpha(logo_alpha)
                logo_x = (w - logo_w) // 2
                logo_y = (h - logo_h) // 2
                screen.blit(logo, (logo_x, logo_y))

            # Draw timer layer
            if timer_alpha > 0:
                target_size = min(int(h * 0.7), int(w * 0.35))
                if display_font is None or display_font_size != target_size:
                    display_font = pygame.font.SysFont(
                        "SF Mono,DejaVu Sans Mono,Consolas,monospace", target_size,
                    )
                    display_font_size = target_size
                time_str = party.display.format_time()
                text_surface = display_font.render(time_str, True, TIMER_COLOR)
                text_surface.set_alpha(timer_alpha)
                rect = text_surface.get_rect(center=(w // 2, h // 2))
                screen.blit(text_surface, rect)

            display_window.flip()

        # -- Push state to web display --
        if web_display is not None:
            from shuffle_party.web_display import DisplayState

            web_display.update(DisplayState(
                state=party.state.name,
                remaining_seconds=party.display.remaining_seconds,
                formatted_time=party.display.format_time(),
                timer_alpha=timer_alpha,
                logo_alpha=logo_alpha,
                crossfading=crossfading,
                crossfade_duration=CROSSFADE_DURATION,
            ))

        # -- Render control panel --
        control.draw()

        clock.tick(30)

    buttons.close()
    extender.close()
    party.lighting.close()
    if web_display is not None:
        web_display.stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    run()
