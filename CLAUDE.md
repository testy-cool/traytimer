# Tray Timer (Linux)

Linux system tray countdown timer with CRT/Pip-Boy aesthetic. Ported from the Windows `taskbartimer` (on SSD at `/media/testycool/SSD/code/taskbartimer/`).

## Architecture

- Single `timer.py` file, Python 3.11+
- `pystray` (appindicator backend) for tray icon, `Pillow` for icon rendering
- GTK3 (PyGObject) for native dialogs — inherits system theme
- Background thread ticks every 1s, re-renders icon and updates tooltip
- State persisted to `timer_state.json` (auto-saved every 30s + on quit/pause/reset)
- On relaunch, elapsed time while closed is subtracted from remaining

## Icon Design

- CRT monitor style: dark bezel frame, colored screen inset, phosphor-glow number
- Screen color lerps teal → amber → red based on urgency
- Scanlines, vignette, and phosphor bloom for the Pip-Boy/Fallout feel
- Rendered at 128px (2x), downscaled to 64px for tray
- Text is always a single digit for readability at small sizes

## Urgency Modes

- **Relative** (default): color based on % of timer remaining
- **Absolute**: color based on remaining time vs a configurable window (e.g. 18h, 3h, 30m). Useful for "countdown to hour" where the timer duration varies but your sense of urgency is fixed.

## Input Formats

- Bare number: minutes (e.g. `25` = 25 min)
- `Nm`: minutes, `Ns`: seconds, `Nh`: hours
- `HH:MM`: countdown to that clock time (wraps to next day if past)

## Dependencies

- Python 3.11+, managed via `uv`
- `pystray`, `pillow`, `PyGObject` (required)
- `mss` (optional, for check-in screenshots; falls back to `scrot`)
- System: `libgirepository-2.0-dev`, `gir1.2-ayatanaappindicator3-0.1`

## Dev Commands

```bash
uv run python timer.py    # run directly
```

## Autostart

Desktop entry at `~/.config/autostart/traytimer.desktop` — launches on login.

## Windows Version

The original Windows version lives at `/media/testycool/SSD/code/taskbartimer/` and on GitHub at `testy-cool/traytimer`. It uses `winsound`, `ctypes`, `ImageGrab`, `os.startfile` — not compatible with this Linux port.

## Files to never commit

- `timer_state.json` (runtime state)
- `screenshots/` (check-in desktop captures)
- `.venv/`
- `__pycache__/`
