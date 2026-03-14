"""Tkinter control panel for Shuffle Partey.

Runs in a separate process to avoid SDL/Tk conflicts on macOS.
Communicates with the main pygame process via multiprocessing shared state.
"""

import multiprocessing as mp
import os


class SharedState:
    """Shared state between the pygame process and the control panel process."""

    def __init__(self, set_duration: int, dj_channels: list[int], shuffle_channels: list[int]) -> None:
        # Read by control panel (updated by main process)
        self.state = mp.Value("i", 0)  # 0 = DJ_SET, 1 = SHUFFLE
        self.remaining_seconds = mp.Value("i", set_duration)
        self.mp3_pos_ms = mp.Value("i", -1)  # -1 = not playing
        self.mp3_duration_ms = mp.Value("i", 0)  # total track length
        self.track_name = mp.Array("c", 256)  # current track filename

        # Written by control panel (read by main process)
        self.new_duration = mp.Value("i", set_duration)
        self.duration_changed = mp.Value("i", 0)  # flag
        self.master_volume = mp.Value("d", 1.0)
        self.volume_changed = mp.Value("i", 0)  # flag

        # Channel info for display
        self.dj_channels = dj_channels
        self.shuffle_channels = shuffle_channels


def _run_panel(shared: SharedState, dj_channels: list[int], shuffle_channels: list[int]) -> None:
    """Entry point for the control panel process."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Shuffle Partey — Controls")
    root.geometry("480x520")
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

    track_name_var = tk.StringVar(value="No track playing")
    ttk.Label(frame_mp3, textvariable=track_name_var, style="Status.TLabel").pack(anchor="w")

    mp3_progress = ttk.Progressbar(frame_mp3, mode="determinate", maximum=100)
    mp3_progress.pack(fill="x", pady=(4, 0))

    mp3_time_var = tk.StringVar(value="")
    ttk.Label(frame_mp3, textvariable=mp3_time_var, style="Status.TLabel").pack(anchor="e")

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
        state_name = "SHUFFLE" if shared.state.value == 1 else "DJ SET"
        state_var.set(state_name)

        # Remaining time
        rem = shared.remaining_seconds.value
        minutes = rem // 60
        seconds = rem % 60
        remaining_var.set(f"{minutes:02d}:{seconds:02d}")

        # MP3 progress
        pos = shared.mp3_pos_ms.value
        duration = shared.mp3_duration_ms.value
        if pos >= 0 and duration > 0:
            pos_s = pos / 1000
            dur_s = duration / 1000
            rem_s = max(0, dur_s - pos_s)

            rem_m = int(rem_s) // 60
            rem_sec = int(rem_s) % 60
            dur_m = int(dur_s) // 60
            dur_sec = int(dur_s) % 60
            mp3_time_var.set(f"-{rem_m:02d}:{rem_sec:02d} / {dur_m:02d}:{dur_sec:02d}")

            name = shared.track_name.value.decode("utf-8", errors="ignore").rstrip("\x00")
            if name:
                track_name_var.set(name)

            pct = min(100, (pos / duration) * 100)
            mp3_progress.configure(mode="determinate", value=pct)
        else:
            mp3_progress.configure(mode="determinate", value=0)
            track_name_var.set("No track playing")
            mp3_time_var.set("")

        # Channel levels
        is_dj = shared.state.value == 0
        dj_level = 100 if is_dj else 0
        shuffle_level = 0 if is_dj else 100
        for ch in dj_channels:
            if ch in level_bars:
                level_bars[ch]["value"] = dj_level
        for ch in shuffle_channels:
            if ch in level_bars:
                level_bars[ch]["value"] = shuffle_level

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

    def update(self) -> None:
        """Called from the main loop to sync state in both directions."""
        from shuffle_party.app import State

        # Push state to control panel
        self.shared.state.value = 1 if self.party.state == State.SHUFFLE else 0
        self.shared.remaining_seconds.value = self.party.display.remaining_seconds

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

        # Pull master volume changes from control panel
        if self.shared.volume_changed.value:
            self.shared.volume_changed.value = 0
            self.party.mixer.set_master_volume(self.shared.master_volume.value)

    def set_track_name(self, track_path: str) -> None:
        """Set the current track name and read its duration."""
        if track_path:
            name = os.path.basename(track_path)
            self.shared.track_name.value = name.encode("utf-8")[:255]
            try:
                from mutagen.mp3 import MP3
                audio = MP3(track_path)
                self.shared.mp3_duration_ms.value = int(audio.info.length * 1000)
            except Exception:
                self.shared.mp3_duration_ms.value = 0
        else:
            self.shared.track_name.value = b"\x00" * 255
            self.shared.mp3_duration_ms.value = 0
