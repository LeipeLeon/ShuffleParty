"""Fullscreen pygame display: countdown timer or shuffle logo."""


class Display:
    """Manages the fullscreen pygame display showing timer or shuffle logo."""

    def __init__(self, set_duration: int) -> None:
        self.set_duration = set_duration
        self.remaining_seconds = set_duration

    def start_timer(self) -> None:
        """Reset and start the countdown timer for a new DJ set."""
        self.remaining_seconds = self.set_duration

    def tick(self) -> bool:
        """Decrement timer by one second. Returns True if timer has expired."""
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
        return self.remaining_seconds == 0

    def change_duration(self, new_duration: int) -> None:
        """Change the set duration. Adjusts remaining time proportionally."""
        elapsed = self.set_duration - self.remaining_seconds
        self.set_duration = new_duration
        self.remaining_seconds = max(0, new_duration - elapsed)

    def format_time(self) -> str:
        """Return remaining time as MM:SS string."""
        minutes = self.remaining_seconds // 60
        seconds = self.remaining_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
