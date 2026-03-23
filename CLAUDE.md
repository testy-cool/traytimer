# Taskbar Timer

Windows 10 system tray countdown timer. Single-file Python app (`timer.py`).

## Architecture
- Single `timer.py` file, ~300 lines
- `pystray` for tray icon, `Pillow` for rendering icon image
- Background thread ticks every 1s, re-renders icon and updates tooltip
- State persisted to `timer_state.json` (auto-saved every 30s + on quit/pause/reset)
- On relaunch, elapsed time while closed is subtracted from remaining

## Icon Design
- 64x64 rendered, Windows scales to tray size
- Shows hours remaining as large centered number (Consolas 42pt)
- Color fill from bottom shrinks like water draining — ratio = remaining/total
- Color gradient: green (full) -> yellow (halfway) -> red (empty), computed via `lerp_color()`
- Flashes red/black when timer hits zero

## Input Formats
- Bare number: minutes (e.g. `25` = 25 min)
- `Nm`: minutes, `Ns`: seconds, `Nh`: hours
- `HH:MM`: countdown to that clock time (wraps to next day if past)

## Launchers
- `timer.vbs`: silent launch (no console window), also in Windows Startup folder
- `timer.bat`: launch with brief console flash

## Dependencies
- Python 3.13+, managed via `uv`
- `pystray`, `pillow` (in pyproject.toml)

## Dev Commands
```bash
uv run python timer.py    # run directly
```

## Files to never commit
- `timer_state.json` (runtime state)
- `.venv/`
