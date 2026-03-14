"""Tkinter control panel for Shuffle Partey.

Runs in a separate thread alongside the pygame main loop. Provides
controls for set duration, master volume, and displays MP3 progress
and channel levels.
"""

import tkinter as tk
from tkinter import ttk
import threading


class ControlPanel:
    """Operator control window using tkinter."""

    def __init__(self, party) -> None:
        self.party = party
        self._root = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._root = tk.Tk()
        self._root.title("Shuffle Partey — Controls")
        self._root.geometry("480x520")
        self._root.resizable(False, False)

        style = ttk.Style()
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"))
        style.configure("Big.TLabel", font=("Helvetica", 24, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 11))

        pad = {"padx": 10, "pady": 4}

        # -- State & remaining time --
        frame_status = ttk.LabelFrame(self._root, text="Status", padding=10)
        frame_status.pack(fill="x", **pad)

        self._state_var = tk.StringVar(value="DJ SET")
        ttk.Label(frame_status, textvariable=self._state_var, style="Status.TLabel").pack(side="left")

        self._remaining_var = tk.StringVar(value="--:--")
        ttk.Label(frame_status, textvariable=self._remaining_var, style="Big.TLabel").pack(side="right")

        # -- Set duration control --
        frame_duration = ttk.LabelFrame(self._root, text="Set Duration", padding=10)
        frame_duration.pack(fill="x", **pad)

        self._duration_var = tk.IntVar(value=self.party.display.set_duration)
        self._duration_label = tk.StringVar(value=self._format_duration(self._duration_var.get()))

        slider_frame = ttk.Frame(frame_duration)
        slider_frame.pack(fill="x")

        ttk.Label(slider_frame, text="5 min").pack(side="left")
        self._duration_slider = ttk.Scale(
            slider_frame,
            from_=5 * 60, to=60 * 60,
            orient="horizontal",
            variable=self._duration_var,
            command=self._on_duration_changed,
        )
        self._duration_slider.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(slider_frame, text="60 min").pack(side="left")

        ttk.Label(frame_duration, textvariable=self._duration_label, style="Status.TLabel").pack()

        # -- MP3 progress --
        frame_mp3 = ttk.LabelFrame(self._root, text="Shuffle Track", padding=10)
        frame_mp3.pack(fill="x", **pad)

        self._track_name_var = tk.StringVar(value="No track playing")
        ttk.Label(frame_mp3, textvariable=self._track_name_var, style="Status.TLabel").pack(anchor="w")

        self._mp3_progress = ttk.Progressbar(frame_mp3, mode="determinate", maximum=100)
        self._mp3_progress.pack(fill="x", pady=(4, 0))

        self._mp3_time_var = tk.StringVar(value="")
        ttk.Label(frame_mp3, textvariable=self._mp3_time_var, style="Status.TLabel").pack(anchor="e")

        # -- Master volume --
        frame_master = ttk.LabelFrame(self._root, text="Master Volume", padding=10)
        frame_master.pack(fill="x", **pad)

        self._master_vol_var = tk.DoubleVar(value=1.0)

        vol_frame = ttk.Frame(frame_master)
        vol_frame.pack(fill="x")

        ttk.Label(vol_frame, text="0%").pack(side="left")
        self._master_slider = ttk.Scale(
            vol_frame,
            from_=0.0, to=1.0,
            orient="horizontal",
            variable=self._master_vol_var,
            command=self._on_master_volume_changed,
        )
        self._master_slider.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(vol_frame, text="100%").pack(side="left")

        self._master_vol_label = tk.StringVar(value="100%")
        ttk.Label(frame_master, textvariable=self._master_vol_label, style="Status.TLabel").pack()

        # -- Channel levels --
        frame_levels = ttk.LabelFrame(self._root, text="Channel Levels", padding=10)
        frame_levels.pack(fill="x", **pad)

        self._level_bars = {}
        channels = [
            ("DJ L", self.party.mixer.dj_channels[0]),
            ("DJ R", self.party.mixer.dj_channels[1]),
            ("Shuffle L", self.party.mixer.shuffle_channels[0]),
            ("Shuffle R", self.party.mixer.shuffle_channels[1]),
        ]
        for label, ch in channels:
            row = ttk.Frame(frame_levels)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{label} (ch {ch})", width=16).pack(side="left")
            bar = ttk.Progressbar(row, mode="determinate", maximum=100, length=200)
            bar.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self._level_bars[ch] = bar

        # Start polling
        self._poll()
        self._root.mainloop()

    def _poll(self) -> None:
        """Update display values from the party state, called every 100ms."""
        if self._root is None:
            return

        try:
            # State
            from shuffle_party.app import State
            state_name = "SHUFFLE" if self.party.state == State.SHUFFLE else "DJ SET"
            self._state_var.set(state_name)

            # Remaining time
            self._remaining_var.set(self.party.display.format_time())

            # MP3 progress
            self._update_mp3_progress()

            # Channel levels (fader positions, not audio meters)
            self._update_channel_levels()

        except Exception:
            pass

        self._root.after(100, self._poll)

    def _update_mp3_progress(self) -> None:
        """Update MP3 progress bar from pygame mixer state."""
        try:
            import pygame
            if pygame.mixer.music.get_busy():
                pos_ms = pygame.mixer.music.get_pos()
                pos_s = max(0, pos_ms / 1000)
                minutes = int(pos_s) // 60
                seconds = int(pos_s) % 60
                self._mp3_time_var.set(f"{minutes:02d}:{seconds:02d}")

                # Show track name if we have one
                if hasattr(self.party, '_current_track') and self.party._current_track:
                    import os
                    name = os.path.basename(self.party._current_track)
                    self._track_name_var.set(name)

                # Progress — we don't know total length from pygame.mixer.music,
                # so show an indeterminate time counter
                self._mp3_progress.configure(mode="indeterminate")
                self._mp3_progress.step(2)
            else:
                if self._mp3_progress.cget("mode") == "indeterminate":
                    self._mp3_progress.stop()
                    self._mp3_progress.configure(mode="determinate", value=0)
                self._track_name_var.set("No track playing")
                self._mp3_time_var.set("")
        except Exception:
            pass

    def _update_channel_levels(self) -> None:
        """Show current fader positions as level indicators."""
        # We read the last-sent fader values. Since we control the faders,
        # we know what they should be based on state.
        from shuffle_party.app import State
        if self.party.state == State.DJ_SET:
            dj_level = 100
            shuffle_level = 0
        else:
            dj_level = 0
            shuffle_level = 100

        for ch in self.party.mixer.dj_channels:
            if ch in self._level_bars:
                self._level_bars[ch]["value"] = dj_level
        for ch in self.party.mixer.shuffle_channels:
            if ch in self._level_bars:
                self._level_bars[ch]["value"] = shuffle_level

    def _on_duration_changed(self, value) -> None:
        """Slider moved — update the set duration."""
        # Round to nearest 30 seconds for usability
        raw = int(float(value))
        rounded = round(raw / 30) * 30
        self._duration_var.set(rounded)
        self._duration_label.set(self._format_duration(rounded))
        self.party.display.change_duration(rounded)

    def _on_master_volume_changed(self, value) -> None:
        """Master volume slider moved."""
        vol = float(value)
        self._master_vol_label.set(f"{int(vol * 100)}%")
        self.party.mixer.set_master_volume(vol)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        m = seconds // 60
        s = seconds % 60
        if s:
            return f"{m} min {s} sec"
        return f"{m} min"
