"""Tkinter control panel for Shuffle Partey.

Runs in a separate process to avoid SDL/Tk conflicts on macOS.
Communicates with the main pygame process via multiprocessing shared state.
"""

import logging
import multiprocessing as mp
import os
import struct
import subprocess

logger = logging.getLogger(__name__)

# Number of bars in the waveform display
WAVEFORM_BINS = 200


class SharedState:
    """Shared state between the pygame process and the control panel process."""

    def __init__(
        self, set_duration: int, dj_channels: list[int], shuffle_channels: list[int],
    ) -> None:
        # Read by control panel (updated by main process)
        self.state = mp.Value("i", 0)  # 0 = DJ_SET, 1 = SHUFFLE
        self.remaining_seconds = mp.Value("i", set_duration)
        self.mp3_pos_ms = mp.Value("i", -1)  # -1 = not playing
        self.mp3_duration_ms = mp.Value("i", 0)  # total track length
        self.track_name = mp.Array("c", 256)  # current track filename
        self.track_display = mp.Array("c", 512)  # "Artist — Title" for display
        self.cover_art = mp.Array("c", 200_000)  # JPEG/PNG cover art bytes
        self.cover_art_size = mp.Value("i", 0)  # actual size of cover art data
        self.track_bpm = mp.Value("d", 0.0)
        self.waveform = mp.Array("f", WAVEFORM_BINS)  # normalized peak values 0.0–1.0
        self.waveform_ready = mp.Value("i", 0)  # flag

        # Written by control panel (read by main process)
        self.new_duration = mp.Value("i", set_duration)
        self.duration_changed = mp.Value("i", 0)  # flag
        self.master_volume = mp.Value("d", 1.0)
        self.volume_changed = mp.Value("i", 0)  # flag
        self.fade_out_now = mp.Value("i", 0)  # flag

        # Fader levels (updated every frame from mixer)
        self.dj_level = mp.Value("d", 1.0)
        self.shuffle_level = mp.Value("d", 0.0)

        # Channel info for display
        self.dj_channels = dj_channels
        self.shuffle_channels = shuffle_channels


def _run_panel(shared: SharedState, dj_channels: list[int], shuffle_channels: list[int]) -> None:
    """Entry point for the control panel process."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Shuffle Partey — Controls")
    root.geometry("480x780")
    root.resizable(False, False)

    style = ttk.Style()
    style.configure("Big.TLabel", font=("Helvetica", 24, "bold"))
    style.configure("Status.TLabel", font=("Helvetica", 11))

    pad = {"padx": 10, "pady": 4}

    # -- State & remaining time --
    frame_status = ttk.LabelFrame(root, text="Status", padding=10)
    frame_status.pack(fill="x", **pad)

    state_var = tk.StringVar(value="DJ SET")
    ttk.Label(frame_status, textvariable=state_var, style="Status.TLabel").pack(side="left")

    remaining_var = tk.StringVar(value="--:--")
    ttk.Label(frame_status, textvariable=remaining_var, style="Big.TLabel").pack(side="right")

    # -- Fade out now button --
    def on_fade_out_now():
        shared.fade_out_now.value = 1

    fade_btn_var = tk.StringVar(value="Fade Out Now")
    fade_btn = ttk.Button(root, textvariable=fade_btn_var, command=on_fade_out_now)
    fade_btn.pack(fill="x", **pad)

    # -- Set duration control --
    frame_duration = ttk.LabelFrame(root, text="Set Duration", padding=10)
    frame_duration.pack(fill="x", **pad)

    duration_var = tk.IntVar(value=shared.new_duration.value)

    def format_duration(seconds):
        m = seconds // 60
        s = seconds % 60
        return f"{m} min {s} sec" if s else f"{m} min"

    duration_label = tk.StringVar(value=format_duration(duration_var.get()))

    slider_frame = ttk.Frame(frame_duration)
    slider_frame.pack(fill="x")
    ttk.Label(slider_frame, text="30s").pack(side="left")

    def on_duration_changed(value):
        raw = int(float(value))
        rounded = round(raw / 30) * 30
        duration_var.set(rounded)
        duration_label.set(format_duration(rounded))
        shared.new_duration.value = rounded
        shared.duration_changed.value = 1

    duration_slider = ttk.Scale(
        slider_frame, from_=30, to=20 * 60,
        orient="horizontal", variable=duration_var,
        command=on_duration_changed,
    )
    duration_slider.pack(side="left", fill="x", expand=True, padx=5)
    ttk.Label(slider_frame, text="20 min").pack(side="left")
    ttk.Label(frame_duration, textvariable=duration_label, style="Status.TLabel").pack()

    # -- MP3 progress --
    frame_mp3 = ttk.LabelFrame(root, text="Shuffle Track", padding=10)
    frame_mp3.pack(fill="x", **pad)

    # Cover art + track info side by side
    track_top = ttk.Frame(frame_mp3)
    track_top.pack(fill="x")

    cover_size = 80
    cover_label = tk.Label(track_top, width=cover_size, height=cover_size, bg="#2a2a3e")
    cover_label.pack(side="left", padx=(0, 8))
    cover_photo_ref = [None]  # keep reference to prevent GC

    # Create a placeholder image for when no cover art is available
    def _make_placeholder():
        from PIL import Image, ImageDraw, ImageFont, ImageTk
        img = Image.new("RGB", (cover_size, cover_size), "#2a2a3e")
        draw = ImageDraw.Draw(img)
        # Draw a music note icon (♪) centered
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Apple Symbols.ttf", 40)
        except Exception:
            font = ImageFont.load_default()
        draw.text(
            (cover_size / 2, cover_size / 2), "\u266b",
            fill="#555570", font=font, anchor="mm",
        )
        return ImageTk.PhotoImage(img)

    try:
        placeholder_photo = _make_placeholder()
    except Exception:
        placeholder_photo = None

    track_info_frame = ttk.Frame(track_top)
    track_info_frame.pack(side="left", fill="x", expand=True)

    track_name_var = tk.StringVar(value="No track loaded")
    ttk.Label(
        track_info_frame, textvariable=track_name_var,
        font=("Helvetica", 12, "bold"), wraplength=340,
    ).pack(anchor="w")

    track_meta_var = tk.StringVar(value="")
    ttk.Label(track_info_frame, textvariable=track_meta_var, style="Status.TLabel").pack(anchor="w")

    mp3_time_var = tk.StringVar(value="")
    ttk.Label(track_info_frame, textvariable=mp3_time_var, style="Status.TLabel").pack(anchor="w")

    waveform_height = 60
    waveform_canvas = tk.Canvas(
        frame_mp3, height=waveform_height, bg="#1a1a2e",
        highlightthickness=0,
    )
    waveform_canvas.pack(fill="x", pady=(4, 0))
    waveform_drawn = [False]
    cover_loaded_for = [b""]  # track which cover is currently shown

    # -- Master volume --
    frame_master = ttk.LabelFrame(root, text="Master Volume", padding=10)
    frame_master.pack(fill="x", **pad)

    master_vol_var = tk.DoubleVar(value=1.0)
    master_vol_label = tk.StringVar(value="100%")

    def on_master_volume_changed(value):
        vol = float(value)
        master_vol_label.set(f"{int(vol * 100)}%")
        shared.master_volume.value = vol
        shared.volume_changed.value = 1

    vol_frame = ttk.Frame(frame_master)
    vol_frame.pack(fill="x")
    ttk.Label(vol_frame, text="0%").pack(side="left")
    ttk.Scale(
        vol_frame, from_=0.0, to=1.0,
        orient="horizontal", variable=master_vol_var,
        command=on_master_volume_changed,
    ).pack(side="left", fill="x", expand=True, padx=5)
    ttk.Label(vol_frame, text="100%").pack(side="left")
    ttk.Label(frame_master, textvariable=master_vol_label, style="Status.TLabel").pack()

    # -- Channel levels --
    frame_levels = ttk.LabelFrame(root, text="Channel Levels", padding=10)
    frame_levels.pack(fill="x", **pad)

    level_bars = {}
    channels = [
        ("DJ L", dj_channels[0]),
        ("DJ R", dj_channels[1]),
        ("Shuffle L", shuffle_channels[0]),
        ("Shuffle R", shuffle_channels[1]),
    ]
    for label, ch in channels:
        row = ttk.Frame(frame_levels)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=f"{label} (ch {ch})", width=16).pack(side="left")
        bar = ttk.Progressbar(row, mode="determinate", maximum=100, length=200)
        bar.pack(side="left", fill="x", expand=True, padx=(5, 0))
        level_bars[ch] = bar

    def poll():
        # State
        is_shuffle = shared.state.value == 1
        state_name = "SHUFFLE" if is_shuffle else "DJ SET"
        state_var.set(state_name)
        fade_btn_var.set("Fade Track Out Now" if is_shuffle else "End DJ Set Now")

        # Remaining time
        rem = shared.remaining_seconds.value
        minutes = rem // 60
        seconds = rem % 60
        remaining_var.set(f"{minutes:02d}:{seconds:02d}")

        # Track info, cover art, and waveform
        raw_name = shared.track_name.value
        name = raw_name.decode("utf-8", errors="ignore").rstrip("\x00")
        display = shared.track_display.value.decode("utf-8", errors="ignore").rstrip("\x00")
        duration = shared.mp3_duration_ms.value
        pos = shared.mp3_pos_ms.value

        if name:
            track_name_var.set(display or name)
            bpm = shared.track_bpm.value
            track_meta_var.set(f"{bpm:.1f} BPM" if bpm > 0 else "")

            # Load cover art once per track
            art_size = shared.cover_art_size.value
            if raw_name != cover_loaded_for[0]:
                cover_loaded_for[0] = raw_name
                waveform_drawn[0] = False
                if art_size > 0:
                    try:
                        import io

                        from PIL import Image, ImageTk
                        art_bytes = bytes(shared.cover_art[:art_size])
                        img = Image.open(io.BytesIO(art_bytes))
                        img = img.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        cover_label.configure(image=photo, width=cover_size, height=cover_size)
                        cover_photo_ref[0] = photo
                    except Exception:
                        cover_label.configure(
                            image=placeholder_photo or "", text="",
                            width=cover_size, height=cover_size,
                        )
                        cover_photo_ref[0] = placeholder_photo
                else:
                    cover_label.configure(
                            image=placeholder_photo or "", text="",
                            width=cover_size, height=cover_size,
                        )
                    cover_photo_ref[0] = placeholder_photo

            # Draw waveform bars once when a new track loads
            if shared.waveform_ready.value and not waveform_drawn[0]:
                waveform_canvas.delete("waveform")
                canvas_w = waveform_canvas.winfo_width() or 460
                bar_w = max(1, canvas_w / WAVEFORM_BINS)
                mid = waveform_height / 2
                peaks = list(shared.waveform[:])
                for i, peak in enumerate(peaks):
                    x = i * bar_w
                    h = peak * mid * 0.9
                    waveform_canvas.create_rectangle(
                        x, mid - h, x + bar_w - 1, mid + h,
                        fill="#4a9eff", outline="", tags="waveform",
                    )
                waveform_drawn[0] = True

            # Playhead and time display (only while playing)
            if pos >= 0 and duration > 0:
                pos_s = pos / 1000
                dur_s = duration / 1000
                rem_s = max(0, dur_s - pos_s)

                rem_m = int(rem_s) // 60
                rem_sec = int(rem_s) % 60
                dur_m = int(dur_s) // 60
                dur_sec = int(dur_s) % 60
                mp3_time_var.set(f"-{rem_m:02d}:{rem_sec:02d} / {dur_m:02d}:{dur_sec:02d}")

                waveform_canvas.delete("playhead")
                canvas_w = waveform_canvas.winfo_width() or 460
                x = (pos / duration) * canvas_w
                waveform_canvas.create_line(
                    x, 0, x, waveform_height,
                    fill="#ff4444", width=2, tags="playhead",
                )
            else:
                waveform_canvas.delete("playhead")
                if duration > 0:
                    dur_m = duration // 60000
                    dur_sec = (duration // 1000) % 60
                    mp3_time_var.set(f"Ready — {dur_m:02d}:{dur_sec:02d}")
                else:
                    mp3_time_var.set("Ready")
        else:
            waveform_canvas.delete("waveform", "playhead")
            waveform_drawn[0] = False
            cover_loaded_for[0] = b""
            cover_label.configure(
                            image=placeholder_photo or "", text="",
                            width=cover_size, height=cover_size,
                        )
            cover_photo_ref[0] = placeholder_photo
            track_name_var.set("No track loaded")
            track_meta_var.set("")
            mp3_time_var.set("")

        # Channel levels
        dj_pct = shared.dj_level.value * 100
        shuffle_pct = shared.shuffle_level.value * 100
        for ch in dj_channels:
            if ch in level_bars:
                level_bars[ch]["value"] = dj_pct
        for ch in shuffle_channels:
            if ch in level_bars:
                level_bars[ch]["value"] = shuffle_pct

        root.after(100, poll)

    poll()
    root.mainloop()


class ControlPanel:
    """Launches the control panel in a separate process."""

    def __init__(self, party) -> None:
        self.party = party
        self.shared = SharedState(
            set_duration=party.display.set_duration,
            dj_channels=party.mixer.dj_channels,
            shuffle_channels=party.mixer.shuffle_channels,
        )
        self._process = mp.Process(
            target=_run_panel,
            args=(self.shared, party.mixer.dj_channels, party.mixer.shuffle_channels),
            daemon=True,
        )
        self._process.start()
        self._fade_out_now = False

    def update(self) -> None:
        """Called from the main loop to sync state in both directions."""
        from shuffle_party.app import State

        # Push state to control panel
        self.shared.state.value = 1 if self.party.state == State.SHUFFLE else 0
        self.shared.remaining_seconds.value = self.party.display.remaining_seconds
        self.shared.dj_level.value = self.party.mixer.dj_level
        self.shared.shuffle_level.value = self.party.mixer.shuffle_level

        # Push MP3 position
        try:
            import pygame
            if pygame.mixer.music.get_busy():
                self.shared.mp3_pos_ms.value = pygame.mixer.music.get_pos()
            else:
                self.shared.mp3_pos_ms.value = -1
        except Exception:
            self.shared.mp3_pos_ms.value = -1

        # Pull duration changes from control panel
        if self.shared.duration_changed.value:
            self.shared.duration_changed.value = 0
            self.party.display.change_duration(self.shared.new_duration.value)

        # Pull fade out now from control panel
        if self.shared.fade_out_now.value:
            self.shared.fade_out_now.value = 0
            self._fade_out_now = True

        # Pull master volume changes from control panel
        if self.shared.volume_changed.value:
            self.shared.volume_changed.value = 0
            self.party.mixer.set_master_volume(self.shared.master_volume.value)

    def should_fade_out_now(self) -> bool:
        """Check and clear the fade-out-now flag."""
        if self._fade_out_now:
            self._fade_out_now = False
            return True
        return False

    def set_track_name(self, track_path: str) -> None:
        """Set track info from ID3 tags, read duration, cover art, and generate waveform."""
        if track_path:
            name = os.path.basename(track_path)
            self.shared.track_name.value = name.encode("utf-8")[:255]
            self.shared.waveform_ready.value = 0
            self.shared.cover_art_size.value = 0
            self.shared.track_bpm.value = 0.0

            try:
                from mutagen.mp3 import MP3  # lazy import: optional dependency
                audio = MP3(track_path)
                self.shared.mp3_duration_ms.value = int(audio.info.length * 1000)

                # Build display string from ID3 tags
                display = name
                if audio.tags:
                    artist = str(audio.tags["TPE1"].text[0]) if "TPE1" in audio.tags else ""
                    title = str(audio.tags["TIT2"].text[0]) if "TIT2" in audio.tags else ""
                    if artist and title:
                        display = f"{artist} — {title}"
                    elif title:
                        display = title
                self.shared.track_display.value = display.encode("utf-8")[:511]

                # Extract cover art and BPM from tags
                if audio.tags:
                    for key in audio.tags:
                        if key.startswith("APIC"):
                            art_data = audio.tags[key].data
                            if len(art_data) <= 200_000:
                                self.shared.cover_art[:len(art_data)] = art_data
                                self.shared.cover_art_size.value = len(art_data)
                            break

                    # Read BPM from Traktor PRIV tag (HBPM chunk)
                    for key in audio.tags:
                        if "TRAKTOR" in key:
                            data = audio.tags[key].data
                            idx = data.find(b"MPBH")
                            if idx >= 0 and idx + 16 <= len(data):
                                bpm = struct.unpack("<f", data[idx + 12:idx + 16])[0]
                                if 30 < bpm < 300:
                                    self.shared.track_bpm.value = bpm
                            break
            except Exception as e:
                logger.warning(f"Could not read MP3 metadata for {track_path} — {e!r}")
                self.shared.mp3_duration_ms.value = 0
                self.shared.track_display.value = name.encode("utf-8")[:511]

            self._generate_waveform(track_path)
        else:
            self.shared.track_name.value = b"\x00" * 255
            self.shared.track_display.value = b"\x00" * 511
            self.shared.mp3_duration_ms.value = 0
            self.shared.cover_art_size.value = 0
            self.shared.track_bpm.value = 0.0
            self.shared.waveform_ready.value = 0

    def _generate_waveform(self, track_path: str) -> None:
        """Generate waveform peak data from an MP3 file."""
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-i", track_path,
                    "-f", "s16le", "-ac", "1", "-ar", "8000",
                    "-v", "quiet", "-"
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                return

            raw = result.stdout
            samples = struct.unpack(f"<{len(raw) // 2}h", raw)

            # Split into bins and compute peak for each
            bin_size = max(1, len(samples) // WAVEFORM_BINS)
            max_val = 32768.0
            for i in range(WAVEFORM_BINS):
                start = i * bin_size
                end = min(start + bin_size, len(samples))
                if start >= len(samples):
                    self.shared.waveform[i] = 0.0
                else:
                    chunk = samples[start:end]
                    peak = max(abs(s) for s in chunk) / max_val
                    self.shared.waveform[i] = min(1.0, peak)

            self.shared.waveform_ready.value = 1
        except Exception as e:
            logger.warning(f"Could not generate waveform for {track_path} — {e!r}")
