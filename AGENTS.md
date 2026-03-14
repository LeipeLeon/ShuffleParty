# Shuffle Party

Autonomous DJ rotation system for Raspberry Pi. Cycles between DJ sets (countdown timer) and shuffle tracks (random pre-recorded audio), controlling audio faders, lighting, and a display.

## Architecture

Two-state machine: `IDLE -> DJ_SET <-> SHUFFLE`

- `app.py` — Main controller (`ShuffleParty`), state machine, coordinates all subsystems
- `mixer.py` — Behringer XR12 fader control via OSC (non-blocking crossfades)
- `lighting.py` — QLC+ lighting scene control via OSC
- `display.py` — Countdown timer logic (pygame rendering separate)
- `track_picker.py` — Random track selection from `tracks/` directory, no repeats until all played
- `config.py` — Environment-variable-based configuration with defaults

## Tech Stack

- Python 3.12+, managed with `uv`
- `pygame-ce` for audio/display
- `python-osc` for QLC+ lighting
- `xair-api` for Behringer XR12 mixer
- `mutagen` for audio metadata

## Development

```bash
uv run pytest          # run tests
uv run ruff check      # lint
uv run mypy src/       # type check (strict mode)
```

## Conventions

- Ruff for linting (line-length 100, rules: E/F/I/N/W/UP)
- mypy strict mode enabled
- Hardware dependencies (XR12, QLC+) degrade gracefully when unreachable
- Tests mock all hardware; use `pytest` (not unittest runner)

## Git Workflow

- Commit after every logically complete unit of work without asking permission
- Only `git add` files you actually modified — never stage files changed by the user, linters, or other processes (use explicit file paths, never `git add -A` or `git add .`)
