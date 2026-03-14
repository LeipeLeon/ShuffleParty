"""Pygame control panel for Shuffle Partey.

Renders a second pygame window with buttons, sliders, waveform, cover art,
and channel levels. Runs in the same process as the main display.
"""

import io
import logging
import os
import struct
import subprocess

import pygame

logger = logging.getLogger(__name__)

# Layout constants
WIDTH = 1280
HEIGHT = 720
WAVEFORM_BINS = WIDTH - 24  # 1px per bar, matching waveform rect width

# Colors
BG = (26, 26, 46)
PANEL_BG = (34, 34, 58)
TEXT = (200, 200, 210)
TEXT_DIM = (120, 120, 140)
ACCENT = (74, 158, 255)
BTN_COLOR = (50, 50, 80)
BTN_HOVER = (65, 65, 100)
SLIDER_TRACK = (50, 50, 70)
SLIDER_FILL = ACCENT
WAVEFORM_COLOR = (74, 158, 255)
WAVEFORM_PAST = (40, 70, 120)
PLAYHEAD_COLOR = (255, 68, 68)
CUE_COLOR = (255, 136, 0)
BAR_BG = (40, 40, 60)
GREEN = (80, 200, 120)
PLACEHOLDER_BG = (42, 42, 62)
PLACEHOLDER_FG = (85, 85, 112)


class ControlPanel:
    """Pygame-based control panel in a second window."""

    def __init__(
        self, party, fullscreen: bool = False, display_index: int | None = None,
    ) -> None:
        self.party = party
        kwargs: dict = {}
        if display_index is not None:
            kwargs["display_index"] = display_index
        self.window = pygame.Window(
            "Shuffle Partey — Controls", size=(WIDTH, HEIGHT), **kwargs,
        )
        if fullscreen:
            self.window.set_fullscreen(True)
        self._surface = self.window.get_surface()

        # Fonts
        self._font_big = pygame.font.SysFont("Helvetica", 28, bold=True)
        self._font_med = pygame.font.SysFont("Helvetica", 14)
        self._font_small = pygame.font.SysFont("Helvetica", 12)
        self._font_track = pygame.font.SysFont("Helvetica", 13, bold=True)

        # Flags (consumed by main loop)
        self._start_dj = False
        self._fade_out_now = False
        self._skip_track = False
        self._fadeout_cue_triggered = False

        # Track metadata
        self._track_display = "No track loaded"
        self._track_name = ""
        self._duration_ms = 0
        self._fadeout_cue_ms = -1
        self._waveform: list[float] = []
        # Seek tracking: get_pos() returns time since play(), not absolute position.
        # After set_pos(), get_pos() keeps counting from where it was.
        # We track the absolute target and the get_pos() reading at seek time.
        self._seek_target_ms = 0     # absolute track position we seeked to
        self._getpos_at_seek_ms = 0  # get_pos() value at the moment of seek
        self._cover_art: pygame.Surface | None = None
        self._placeholder = self._make_placeholder()

        # Slider state
        self._duration_value = party.display.set_duration
        self._volume_value = 1.0
        self._dragging: str | None = None  # "duration" or "volume"

        # Set by main loop
        self.crossfading = False

        # Dynamic layout rects (updated each draw)
        self._dur_slider_rect = pygame.Rect(0, 0, 0, 0)
        self._vol_slider_rect = pygame.Rect(0, 0, 0, 0)
        self._waveform_rect = pygame.Rect(0, 0, 0, 0)
        self._pause_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._skip_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._hw_btn_rects: dict[str, pygame.Rect] = {}
        self._paused = False

    def _make_placeholder(self) -> pygame.Surface:
        """Create an 80x80 placeholder surface with a music note icon."""
        surf = pygame.Surface((80, 80))
        surf.fill(PLACEHOLDER_BG)
        # Draw a simple music note: oval head + stem
        color = (90, 90, 120)
        pygame.draw.ellipse(surf, color, (28, 42, 18, 14))
        pygame.draw.line(surf, color, (45, 46), (45, 20), 3)
        pygame.draw.line(surf, color, (45, 20), (55, 24), 3)
        return surf

    def _playback_pos_ms(self) -> int:
        """Current absolute playback position in ms. Returns -1 if not loaded."""
        if not self._track_name:
            return -1
        if not pygame.mixer.music.get_busy() and not self._paused:
            return self._seek_target_ms
        elapsed = max(0, pygame.mixer.music.get_pos() - self._getpos_at_seek_ms)
        return self._seek_target_ms + elapsed

    # -- Public interface (same as before) --

    def should_start_dj(self) -> bool:
        if self._start_dj:
            self._start_dj = False
            return True
        return False

    def should_skip_track(self) -> bool:
        if self._skip_track:
            self._skip_track = False
            return True
        return False

    def should_fade_out_now(self) -> bool:
        if self._fade_out_now:
            self._fade_out_now = False
            return True
        return False

    def update(self) -> None:
        """Check fadeout cue, apply pending slider changes."""
        # Fadeout cue check
        if self._fadeout_cue_ms >= 0 and not self._fadeout_cue_triggered:
            pos = self._playback_pos_ms()
            if pos >= self._fadeout_cue_ms:
                self._fadeout_cue_triggered = True
                self._fade_out_now = True

    def set_track_name(self, track_path: str) -> None:
        """Load track metadata, cover art, and waveform."""
        self._fadeout_cue_triggered = False
        self._seek_target_ms = 0
        self._getpos_at_seek_ms = 0
        self._paused = False
        self._waveform = []
        self._cover_art = None
        self._fadein_cue_ms = -1
        self._fadeout_cue_ms = -1

        if not track_path:
            self._track_name = ""
            self._track_display = "No track loaded"
            self._duration_ms = 0
            return

        name = os.path.basename(track_path)
        self._track_name = name
        self._track_display = name
        self._duration_ms = 0

        try:
            from mutagen.mp3 import MP3
            audio = MP3(track_path)
            self._duration_ms = int(audio.info.length * 1000)

            # Display string from ID3
            if audio.tags:
                artist = str(audio.tags["TPE1"].text[0]) if "TPE1" in audio.tags else ""
                title = str(audio.tags["TIT2"].text[0]) if "TIT2" in audio.tags else ""
                if artist and title:
                    self._track_display = f"{artist} — {title}"
                elif title:
                    self._track_display = title

                # Cover art
                for key in audio.tags:
                    if key.startswith("APIC"):
                        try:
                            art_bytes = audio.tags[key].data
                            img = pygame.image.load(io.BytesIO(art_bytes))
                            self._cover_art = pygame.transform.smoothscale(img, (80, 80))
                        except Exception:
                            pass
                        break

                # Fade cues
                for key in audio.tags:
                    if key.startswith("TXXX:"):
                        tag_upper = key.upper()
                        try:
                            ms = int(audio.tags[key].text[0])
                        except (ValueError, IndexError):
                            continue
                        if "FADEIN" in tag_upper and 0 < ms < self._duration_ms:
                            self._fadein_cue_ms = ms
                        elif "FADEOUT" in tag_upper and 0 < ms < self._duration_ms:
                            self._fadeout_cue_ms = ms

            # Place playhead at fadein point so playback starts there
            if self._fadein_cue_ms > 0:
                self._seek_target_ms = self._fadein_cue_ms
                logger.info(f"Fadein cue at {self._fadein_cue_ms / 1000:.1f}s for {name}")
            if self._fadeout_cue_ms >= 0:
                logger.info(f"Fadeout cue at {self._fadeout_cue_ms / 1000:.1f}s for {name}")
        except Exception as e:
            logger.warning(f"Could not read MP3 metadata for {track_path} — {e!r}")

        self._generate_waveform(track_path)

    def _generate_waveform(self, track_path: str) -> None:
        """Generate waveform peak data from an MP3 file via ffmpeg."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", track_path,
                 "-f", "s16le", "-ac", "1", "-ar", "8000",
                 "-v", "quiet", "-"],
                capture_output=True,
            )
            if result.returncode != 0:
                return

            raw = result.stdout
            samples = struct.unpack(f"<{len(raw) // 2}h", raw)
            bin_size = max(1, len(samples) // WAVEFORM_BINS)
            max_val = 32768.0
            peaks = []
            for i in range(WAVEFORM_BINS):
                start = i * bin_size
                end = min(start + bin_size, len(samples))
                if start >= len(samples):
                    peaks.append(0.0)
                else:
                    chunk = samples[start:end]
                    peaks.append(min(1.0, max(abs(s) for s in chunk) / max_val))
            self._waveform = peaks
        except Exception as e:
            logger.warning(f"Could not generate waveform for {track_path} — {e!r}")

    # -- Event handling --

    def handle_event(self, event: pygame.event.Event) -> None:
        """Process mouse events for buttons and sliders."""
        from shuffle_party.app import State

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            if self._dur_slider_rect.collidepoint(x, y):
                self._dragging = "duration"
                self._update_slider("duration", x, self._dur_slider_rect)
                return
            if self._vol_slider_rect.collidepoint(x, y):
                self._dragging = "volume"
                self._update_volume_slider(y)
                return
            if (self._skip_btn_rect.collidepoint(x, y)
                    and self.party.state == State.DJ_SET
                    and not self.crossfading):
                self._skip_track = True
                return
            if (self._pause_btn_rect.collidepoint(x, y)
                    and self.party.state == State.SHUFFLE):
                if self._paused:
                    pygame.mixer.music.unpause()
                    self._paused = False
                else:
                    pygame.mixer.music.pause()
                    self._paused = True
                return
            if self._waveform_rect.collidepoint(x, y) and self._duration_ms > 0:
                t = (x - self._waveform_rect.x) / self._waveform_rect.width
                seek_ms = int(t * self._duration_ms)
                if pygame.mixer.music.get_busy() or self._paused:
                    self._getpos_at_seek_ms = pygame.mixer.music.get_pos()
                    self._seek_target_ms = seek_ms
                    pygame.mixer.music.set_pos(seek_ms / 1000.0)
                return
            # Virtual reTerminal buttons
            for action, rect in self._hw_btn_rects.items():
                if rect.collidepoint(x, y):
                    if action == "volume_down":
                        self.nudge_volume(-0.05)
                    elif action == "volume_up":
                        self.nudge_volume(0.05)
                    elif action == "skip_track":
                        if self.party.state == State.DJ_SET and not self.crossfading:
                            self._skip_track = True
                    elif action == "crossfade":
                        if self.party.state == State.IDLE:
                            self._start_dj = True
                        else:
                            self._fade_out_now = True
                    return

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging = None

        elif event.type == pygame.MOUSEMOTION:
            x, y = event.pos
            if self._dragging == "duration":
                self._update_slider("duration", x, self._dur_slider_rect)
            elif self._dragging == "volume":
                self._update_volume_slider(y)

    def nudge_volume(self, delta: float) -> None:
        """Adjust master volume by delta (e.g. +0.05 or -0.05), clamped to 0.0–1.0."""
        self._volume_value = max(0.0, min(1.0, round(self._volume_value + delta, 2)))
        self.party.mixer.set_master_volume(self._volume_value)

    def _update_volume_slider(self, mouse_y: int) -> None:
        rect = self._vol_slider_rect
        # Invert: top of rect = 1.0, bottom = 0.0
        t = 1.0 - max(0.0, min(1.0, (mouse_y - rect.y) / rect.height))
        self._volume_value = round(t, 2)
        self.party.mixer.set_master_volume(self._volume_value)

    def _update_slider(self, name: str, mouse_x: int, rect: pygame.Rect) -> None:
        t = max(0.0, min(1.0, (mouse_x - rect.x) / rect.width))
        if name == "duration":
            raw = int(30 + t * (20 * 60 - 30))
            rounded = round(raw / 30) * 30
            self._duration_value = max(30, min(20 * 60, rounded))
            self.party.display.change_duration(self._duration_value)
        elif name == "volume":
            self._volume_value = round(t, 2)
            self.party.mixer.set_master_volume(self._volume_value)

    # -- Drawing --

    def draw(self) -> None:
        """Render the entire control panel."""
        from shuffle_party.app import State

        surf = self.window.get_surface()
        surf.fill(BG)
        w = surf.get_width()

        state = self.party.state
        y = 10

        # -- Status bar --
        state_names = {State.IDLE: "IDLE", State.DJ_SET: "DJ SET", State.SHUFFLE: "SHUFFLE"}
        state_text = self._font_med.render(state_names[state], True, TEXT)
        surf.blit(state_text, (12, y + 4))
        y = 30

        # -- Track info --
        self._draw_section_label(surf, "Shuffle Track", y)
        y += 20

        # Cover art
        cover = self._cover_art or self._placeholder
        surf.blit(cover, (12, y))

        # Track name + time
        display = self._track_display
        name_text = self._font_track.render(display, True, TEXT)
        # Clip to available width
        max_w = w - 110
        if name_text.get_width() > max_w:
            # Truncate with ellipsis
            for end in range(len(display), 0, -1):
                t_surf = self._font_track.render(display[:end] + "...", True, TEXT)
                if t_surf.get_width() <= max_w:
                    name_text = t_surf
                    break
        surf.blit(name_text, (100, y + 2))

        time_label = self._get_time_label()
        if time_label:
            t_text = self._font_med.render(time_label, True, TEXT)
            surf.blit(t_text, (100, y + 20))

        # Cue point times
        cue_parts = []
        if self._fadein_cue_ms > 0:
            s = self._fadein_cue_ms // 1000
            cue_parts.append(f"In: {s // 60}:{s % 60:02d}")
        if self._fadeout_cue_ms >= 0:
            s = self._fadeout_cue_ms // 1000
            cue_parts.append(f"Out: {s // 60}:{s % 60:02d}")
        if cue_parts:
            cue_text = self._font_small.render("  ".join(cue_parts), True, TEXT_DIM)
            surf.blit(cue_text, (100, y + 38))

        # Pause/play button (SHUFFLE only) and Skip button (DJ_SET only)
        btn_y = y + 54
        self._pause_btn_rect = pygame.Rect(100, btn_y, 24, 24)
        self._skip_btn_rect = pygame.Rect(100, btn_y, 80, 24)
        if self._track_name and state == State.SHUFFLE:
            pb = self._pause_btn_rect
            pygame.draw.rect(surf, BTN_COLOR, pb, border_radius=3)
            if self._paused:
                # Play triangle
                pygame.draw.polygon(surf, TEXT, [
                    (pb.x + 8, pb.y + 5), (pb.x + 8, pb.y + 19), (pb.x + 19, pb.y + 12),
                ])
            else:
                # Pause bars
                pygame.draw.rect(surf, TEXT, (pb.x + 7, pb.y + 5, 4, 14))
                pygame.draw.rect(surf, TEXT, (pb.x + 13, pb.y + 5, 4, 14))
        elif self._track_name and state == State.DJ_SET and not self.crossfading:
            sb = self._skip_btn_rect
            pygame.draw.rect(surf, BTN_COLOR, sb, border_radius=3)
            skip_text = self._font_small.render("Skip Track", True, TEXT)
            surf.blit(skip_text, skip_text.get_rect(center=sb.center))

        y += 88

        # Waveform
        wf_rect = pygame.Rect(12, y, w - 24, 60)
        self._waveform_rect = wf_rect
        pygame.draw.rect(surf, PANEL_BG, wf_rect)
        if self._waveform:
            self._draw_waveform(surf, wf_rect)
        y += 68

        # -- Faders (left-aligned) + countdown timer (right) --
        self._draw_section_label(surf, "Levels", y)
        y += 18
        h = surf.get_height()
        btn_h = 56
        fader_h = h - btn_h - y - 30
        faders = [
            ("Master", self._volume_value, ACCENT, True),
            ("Shuffle", self.party.mixer.shuffle_level, ACCENT, False),
            ("DJ", self.party.mixer.dj_level, GREEN, False),
        ]
        fader_spacing = 60
        for i, (label, level, color, is_master) in enumerate(faders):
            cx = 12 + i * fader_spacing + fader_spacing // 2
            bar_w = 24 if is_master else 40
            self._draw_vertical_bar(
                surf, cx, y, bar_w, fader_h, label, level, color, is_master,
            )
        # Store volume slider rect for hit testing (the master fader)
        master_cx = 12 + fader_spacing // 2
        self._vol_slider_rect = pygame.Rect(master_cx - 12, y, 24, fader_h)

        # -- Countdown timer in remaining space --
        timer_x = 12 + len(faders) * fader_spacing + 20
        timer_w = w - timer_x - 12
        timer_cy = y + fader_h // 2
        rem = self.party.display.remaining_seconds
        time_str = f"{rem // 60:02d}:{rem % 60:02d}"
        timer_font_size = min(int(fader_h * 0.6), int(timer_w * 0.4))
        timer_font = pygame.font.Font(None, max(40, timer_font_size))
        timer_text = timer_font.render(time_str, True, TEXT)
        surf.blit(timer_text, timer_text.get_rect(center=(timer_x + timer_w // 2, timer_cy)))
        y += fader_h + 8

        # -- Virtual reTerminal buttons (pinned to bottom, 6 equal columns, last 4 are buttons) --
        btn_y = h - btn_h
        col_w = w // 6

        # -- Duration slider (in the left 2 columns of the footer) --
        dur_x = 20
        dur_w = col_w * 2 - 40
        dur_cy = btn_y + btn_h // 2
        self._dur_slider_rect = pygame.Rect(dur_x, dur_cy - 8, dur_w, 16)
        dur_rect = self._dur_slider_rect
        t = (self._duration_value - 30) / (20 * 60 - 30)
        self._draw_slider(surf, dur_rect, t, "30s", "20m")
        m, s = divmod(self._duration_value, 60)
        dur_label = f"{m}:{s:02d}" if s else f"{m} min"
        dur_text = self._font_small.render(dur_label, True, TEXT_DIM)
        surf.blit(dur_text, (dur_x + dur_w // 2 - dur_text.get_width() // 2, dur_cy + 12))
        label_text = self._font_small.render("Set Duration", True, TEXT_DIM)
        surf.blit(label_text, (dur_x + dur_w // 2 - label_text.get_width() // 2, dur_cy - 24))
        self._hw_btn_rects = {}

        hw_buttons = [
            ("volume_down", 2),
            ("volume_up", 3),
            ("skip_track", 4),
            ("crossfade", 5),
        ]
        for action, col in hw_buttons:
            rect = pygame.Rect(col * col_w, btn_y, col_w, btn_h)
            self._hw_btn_rects[action] = rect
            # Button background with subtle separator
            pygame.draw.rect(surf, BTN_COLOR, rect)
            pygame.draw.line(surf, SLIDER_TRACK, (rect.x, rect.y), (rect.x, rect.bottom), 1)
            # Draw icon centered in button
            cx, cy = rect.centerx, rect.centery
            if action == "volume_down":
                # Speaker with minus: speaker body + cone + minus sign
                pygame.draw.rect(surf, TEXT, (cx - 14, cy - 5, 8, 10))
                pygame.draw.polygon(surf, TEXT, [
                    (cx - 6, cy - 5), (cx + 2, cy - 12), (cx + 2, cy + 12), (cx - 6, cy + 5),
                ])
                pygame.draw.line(surf, TEXT, (cx + 8, cy), (cx + 16, cy), 2)
            elif action == "volume_up":
                # Speaker with plus
                pygame.draw.rect(surf, TEXT, (cx - 14, cy - 5, 8, 10))
                pygame.draw.polygon(surf, TEXT, [
                    (cx - 6, cy - 5), (cx + 2, cy - 12), (cx + 2, cy + 12), (cx - 6, cy + 5),
                ])
                pygame.draw.line(surf, TEXT, (cx + 8, cy), (cx + 16, cy), 2)
                pygame.draw.line(surf, TEXT, (cx + 12, cy - 4), (cx + 12, cy + 4), 2)
            elif action == "skip_track":
                # Skip forward: double triangle + bar
                pygame.draw.polygon(surf, TEXT, [
                    (cx - 10, cy - 10), (cx + 2, cy), (cx - 10, cy + 10),
                ])
                pygame.draw.polygon(surf, TEXT, [
                    (cx + 2, cy - 10), (cx + 14, cy), (cx + 2, cy + 10),
                ])
                pygame.draw.rect(surf, TEXT, (cx + 14, cy - 10, 3, 20))
            elif action == "crossfade":
                # Two overlapping arrows (crossfade symbol)
                if state == State.IDLE:
                    # Play triangle
                    pygame.draw.polygon(surf, TEXT, [
                        (cx - 10, cy - 14), (cx + 14, cy), (cx - 10, cy + 14),
                    ])
                else:
                    # Crossing arrows: right arrow on top, left arrow on bottom
                    pygame.draw.line(surf, TEXT, (cx - 12, cy - 6), (cx + 12, cy - 6), 2)
                    pygame.draw.polygon(surf, TEXT, [
                        (cx + 8, cy - 12), (cx + 16, cy - 6), (cx + 8, cy),
                    ])
                    pygame.draw.line(surf, TEXT, (cx + 12, cy + 6), (cx - 12, cy + 6), 2)
                    pygame.draw.polygon(surf, TEXT, [
                        (cx - 8, cy), (cx - 16, cy + 6), (cx - 8, cy + 12),
                    ])

        # Top border across all buttons
        pygame.draw.line(surf, SLIDER_TRACK, (0, btn_y), (w, btn_y), 1)

        self.window.flip()

    def _draw_section_label(self, surf: pygame.Surface, text: str, y: int) -> None:
        label = self._font_small.render(text, True, TEXT_DIM)
        surf.blit(label, (12, y))

    def _draw_slider(
        self, surf: pygame.Surface, rect: pygame.Rect, t: float,
        left_label: str, right_label: str,
    ) -> None:
        # Labels
        l_text = self._font_small.render(left_label, True, TEXT_DIM)
        r_text = self._font_small.render(right_label, True, TEXT_DIM)
        surf.blit(l_text, (rect.x - l_text.get_width() - 6, rect.y))
        surf.blit(r_text, (rect.right + 6, rect.y))
        # Track
        pygame.draw.rect(surf, SLIDER_TRACK, rect, border_radius=4)
        # Fill
        fill_w = int(rect.width * t)
        if fill_w > 0:
            fill_rect = pygame.Rect(rect.x, rect.y, fill_w, rect.height)
            pygame.draw.rect(surf, SLIDER_FILL, fill_rect, border_radius=4)
        # Handle
        hx = rect.x + fill_w
        pygame.draw.circle(surf, TEXT, (hx, rect.centery), 8)

    def _draw_waveform(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        n = len(self._waveform)
        if n == 0:
            return
        bar_w = rect.width / n
        mid = rect.centery
        half_h = rect.height / 2

        pos_ms = self._playback_pos_ms()
        pos_bin = -1
        if pos_ms >= 0 and self._duration_ms > 0:
            pos_bin = int((pos_ms / self._duration_ms) * n)

        for i, peak in enumerate(self._waveform):
            x = rect.x + int(i * bar_w)
            h = int(peak * half_h * 0.9)
            color = WAVEFORM_PAST if (pos_bin >= 0 and i < pos_bin) else WAVEFORM_COLOR
            if h > 0:
                pygame.draw.rect(surf, color, (x, mid - h, max(1, int(bar_w) - 1), h * 2))

        # Fadein cue marker (green dashed)
        if self._fadein_cue_ms > 0 and self._duration_ms > 0:
            cue_x = rect.x + int((self._fadein_cue_ms / self._duration_ms) * rect.width)
            for dy in range(0, rect.height, 6):
                pygame.draw.line(surf, (0, 200, 120), (cue_x, rect.y + dy),
                                 (cue_x, rect.y + min(dy + 3, rect.height)), 2)

        # Fadeout cue marker (orange dashed)
        if self._fadeout_cue_ms >= 0 and self._duration_ms > 0:
            cue_x = rect.x + int((self._fadeout_cue_ms / self._duration_ms) * rect.width)
            for dy in range(0, rect.height, 6):
                pygame.draw.line(surf, CUE_COLOR, (cue_x, rect.y + dy),
                                 (cue_x, rect.y + min(dy + 3, rect.height)), 2)

        # Playhead
        if pos_bin >= 0:
            px = rect.x + int((pos_ms / self._duration_ms) * rect.width)
            pygame.draw.line(surf, PLAYHEAD_COLOR, (px, rect.y), (px, rect.bottom), 2)

    def _draw_vertical_bar(
        self, surf: pygame.Surface, cx: int, y: int, bar_w: int, h: int,
        label: str, level: float, color: tuple, is_master: bool,
    ) -> None:
        """Draw a vertical level bar. Wider bars for DJ/Shuffle, narrow with handle for master."""
        label_y = y + h + 4
        track_x = cx - bar_w // 2

        # Track background
        track_rect = pygame.Rect(track_x, y + 22, bar_w, h - 38)
        pygame.draw.rect(surf, SLIDER_TRACK, track_rect, border_radius=3)

        # Fill from bottom
        fill_h = int(track_rect.height * level)
        if fill_h > 0:
            fill_rect = pygame.Rect(
                track_rect.x, track_rect.bottom - fill_h, bar_w, fill_h,
            )
            pygame.draw.rect(surf, color, fill_rect, border_radius=3)

        # Fader knob (only for master) — rectangular with grip lines
        if is_master:
            hy = track_rect.bottom - fill_h
            knob_w = bar_w + 16
            knob_h = 20
            knob_rect = pygame.Rect(cx - knob_w // 2, hy - knob_h // 2, knob_w, knob_h)
            # Body
            pygame.draw.rect(surf, (180, 180, 190), knob_rect, border_radius=3)
            # Darker edge
            pygame.draw.rect(surf, (120, 120, 130), knob_rect, width=1, border_radius=3)
            # Center line
            pygame.draw.line(
                surf, (80, 80, 90),
                (knob_rect.x + 6, hy), (knob_rect.right - 6, hy), 1,
            )
            # Grip lines above and below center
            for dy in (-3, 3):
                pygame.draw.line(
                    surf, (140, 140, 150),
                    (knob_rect.x + 6, hy + dy), (knob_rect.right - 6, hy + dy), 1,
                )

        # Value label on top
        val_text = self._font_small.render(f"{int(level * 100)}%", True, TEXT_DIM)
        surf.blit(val_text, (cx - val_text.get_width() // 2, y))

        # Icon or name label on bottom
        if label == "Shuffle":
            self._draw_mirrorball_icon(surf, cx, label_y + 8, 8)
        elif label == "DJ":
            self._draw_dj_icon(surf, cx, label_y + 8, 8)
        else:
            name_text = self._font_small.render(label, True, TEXT_DIM)
            surf.blit(name_text, (cx - name_text.get_width() // 2, label_y))

    def _draw_mirrorball_icon(
        self, surf: pygame.Surface, cx: int, cy: int, r: int,
    ) -> None:
        """Draw a mirrorball icon: circle with grid lines and sparkles."""
        color = (160, 160, 180)
        dim = (100, 100, 120)
        sparkle = (220, 220, 240)
        # Main sphere
        pygame.draw.circle(surf, dim, (cx, cy), r)
        pygame.draw.circle(surf, color, (cx, cy), r, 1)
        # Horizontal bands
        for dy in (-r * 2 // 3, 0, r * 2 // 3):
            half_w = int((r**2 - dy**2) ** 0.5) if abs(dy) < r else 0
            if half_w > 0:
                pygame.draw.line(surf, color, (cx - half_w, cy + dy), (cx + half_w, cy + dy), 1)
        # Vertical bands
        for dx in (-r * 2 // 3, 0, r * 2 // 3):
            half_h = int((r**2 - dx**2) ** 0.5) if abs(dx) < r else 0
            if half_h > 0:
                pygame.draw.line(surf, color, (cx + dx, cy - half_h), (cx + dx, cy + half_h), 1)
        # Sparkles
        for sx, sy in [(-r - 3, -r + 1), (r + 2, -r - 2), (r + 4, r - 3)]:
            pygame.draw.line(surf, sparkle, (cx + sx - 2, cy + sy), (cx + sx + 2, cy + sy), 1)
            pygame.draw.line(surf, sparkle, (cx + sx, cy + sy - 2), (cx + sx, cy + sy + 2), 1)

    def _draw_dj_icon(
        self, surf: pygame.Surface, cx: int, cy: int, r: int,
    ) -> None:
        """Draw a DJ icon: headphones over a record."""
        color = (160, 160, 180)
        dim = (100, 100, 120)
        # Record (vinyl)
        pygame.draw.circle(surf, dim, (cx, cy + 2), r)
        pygame.draw.circle(surf, color, (cx, cy + 2), r, 1)
        pygame.draw.circle(surf, color, (cx, cy + 2), r // 3, 1)
        pygame.draw.circle(surf, (140, 140, 160), (cx, cy + 2), 1)
        # Headphones arc
        arc_r = r - 1
        arc_rect = pygame.Rect(cx - arc_r, cy - r - arc_r + 2, arc_r * 2, arc_r * 2)
        pygame.draw.arc(surf, color, arc_rect, 0.3, 2.84, 2)
        # Ear cups
        cup_w, cup_h = 4, 5
        pygame.draw.rect(surf, color, (cx - arc_r - 1, cy - r + 1, cup_w, cup_h), border_radius=1)
        pygame.draw.rect(surf, color, (cx + arc_r - cup_w + 2, cy - r + 1, cup_w, cup_h),
                         border_radius=1)

    def _get_time_label(self) -> str:
        if not self._track_name:
            return ""
        end_ms = self._fadeout_cue_ms if self._fadeout_cue_ms >= 0 else self._duration_ms
        pos = self._playback_pos_ms()
        if pos >= 0 and end_ms > 0:
            rem_s = max(0, (end_ms - pos) / 1000)
            return f"-{int(rem_s) // 60:02d}:{int(rem_s) % 60:02d}"
        if end_ms > 0:
            return f"Ready — {end_ms // 60000:02d}:{(end_ms // 1000) % 60:02d}"
        return "Ready"
