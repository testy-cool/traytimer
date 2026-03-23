# Taskbar Timer

A Windows 10 system tray countdown timer. Shows hours remaining as a number inside a color fill that drains like water from a glass as time passes.

Inspired by [traytimer](https://github.com/intekhabrizvi/traytimer) (Linux), ported to Windows.

## Features

- **Visual countdown** — tray icon with color fill that shrinks over time (green -> yellow -> red)
- **Set duration** — minutes (`25`), hours (`2h`), seconds (`90s`), or target time (`14:30`)
- **Preset durations** — 5, 10, 15, 25, 30, 45, 60, 90, 120 min via right-click menu
- **Hover tooltip** — shows remaining time + elapsed time
- **Pause/Resume/Reset** — right-click menu
- **Persistent** — timer survives app restarts, adjusts for time elapsed while closed
- **Auto-start** — optional Windows startup via included VBS launcher
- **Alert** — beep + flashing icon when timer completes

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
git clone https://github.com/vladstudio/taskbartimer.git
cd taskbartimer
uv sync
```

## Run

```bash
uv run python timer.py
```

Or double-click `timer.vbs` for a silent launch (no console window).

## Auto-start with Windows

Copy `timer.vbs` to your Startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```
