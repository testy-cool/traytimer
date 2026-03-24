import math
import threading
import time
import json
import re
import os
import winsound
import ctypes
from datetime import datetime, timedelta
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

# DPI awareness
ctypes.windll.shcore.SetProcessDpiAwareness(1)

SIZE = 64
STATE_FILE = Path(__file__).parent / "timer_state.json"

state = {
    "total": 0,
    "remaining": 0,
    "paused": False,
    "running": False,
    "flash": False,
    "started_at": 0,
}
icon_ref = None


def save_state():
    """Persist timer state to disk."""
    try:
        data = {
            "total": state["total"],
            "remaining": state["remaining"],
            "paused": state["paused"],
            "running": state["running"],
            "started_at": state["started_at"],
            "saved_at": time.time(),
        }
        STATE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


def load_state():
    """Restore timer state from disk, adjusting for elapsed time while closed."""
    try:
        if not STATE_FILE.exists():
            return
        data = json.loads(STATE_FILE.read_text())
        if not data.get("running"):
            return
        elapsed_while_closed = time.time() - data.get("saved_at", time.time())
        if data.get("paused"):
            # Was paused — restore as-is
            state["total"] = data["total"]
            state["remaining"] = data["remaining"]
            state["paused"] = True
            state["running"] = True
            state["started_at"] = data.get("started_at", 0)
        else:
            # Was running — subtract time that passed while app was closed
            remaining = data["remaining"] - int(elapsed_while_closed)
            if remaining > 0:
                state["total"] = data["total"]
                state["remaining"] = remaining
                state["running"] = True
                state["paused"] = False
                state["started_at"] = data.get("started_at", 0)
            else:
                # Timer expired while closed
                state["total"] = data["total"]
                state["remaining"] = 0
                state["running"] = True
                state["flash"] = True
                state["started_at"] = data.get("started_at", 0)
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass


def lerp_color(ratio):
    """Green (ratio=1.0) → Yellow (ratio=0.5) → Red (ratio=0.0)"""
    if ratio > 0.5:
        t = (ratio - 0.5) * 2
        return (int(40 + (220 - 40) * (1 - t)), int(200 + (180 - 200) * (1 - t)), int(100 * t))
    else:
        t = ratio * 2
        return (220, int(50 + (180 - 50) * t), int(30 * t))


def render_icon():
    S = SIZE * 2  # 2x render for anti-aliased downscale
    img = Image.new("RGBA", (S, S), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)

    if state["running"] or state["remaining"] > 0:
        ratio = state["remaining"] / max(state["total"], 1)
        fill_h = int(S * ratio)

        # Tailwind colors
        if state["flash"]:
            pulse = (math.sin(time.time() * 4) + 1) / 2
            color = (int(55 + 184 * pulse), int(20 * pulse), int(20 * pulse))  # red pulse
        elif ratio > 0.5:
            color = (16, 185, 129)   # emerald-500
        elif ratio > 0.2:
            color = (245, 158, 11)   # amber-500
        else:
            color = (239, 68, 68)    # red-500

        draw.rectangle([0, S - fill_h, S, S], fill=color)

    # Text
    hours = max(0, state["remaining"]) // 3600
    text = str(hours) if (state["remaining"] > 0 or state["running"]) else "--"

    try:
        font = ImageFont.truetype("segoeuib.ttf", 84)
    except OSError:
        try:
            font = ImageFont.truetype("consola.ttf", 84)
        except OSError:
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (S - tw) // 2 - bbox[0]
    y = (S - th) // 2 - bbox[1] + 2
    draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 120), font=font)
    draw.text((x, y), text, fill="white", font=font)

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    return img


def get_tooltip():
    if state["remaining"] > 0 or state["running"]:
        r = max(0, state["remaining"])
        h, m = r // 3600, (r % 3600) // 60
        if h > 0:
            remaining = f"{h}h {m:02d}m remaining"
        else:
            s = r % 60
            remaining = f"{m}m {s:02d}s remaining"
        elapsed = int(time.time() - state["started_at"]) if state["started_at"] else 0
        eh, em = elapsed // 3600, (elapsed % 3600) // 60
        if eh > 0:
            elapsed_str = f"{eh}h {em:02d}m elapsed"
        else:
            es = elapsed % 60
            elapsed_str = f"{em}m {es:02d}s elapsed"
        return f"{remaining} | {elapsed_str}"
    return "Taskbar Timer"


def parse_time(s):
    s = s.strip()
    if m := re.match(r"^(\d{1,2}):(\d{2})$", s):
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            diff = int((target - now).total_seconds())
            if diff > 0:
                return diff
    if m := re.match(r"^(\d+)\s*s$", s, re.I):
        return int(m.group(1))
    if m := re.match(r"^(\d+)\s*m$", s, re.I):
        return int(m.group(1)) * 60
    if m := re.match(r"^(\d+)\s*h$", s, re.I):
        return int(m.group(1)) * 3600
    if m := re.match(r"^(\d+)$", s):
        return int(m.group(1)) * 60
    return None


def start_timer(secs):
    state["total"] = secs
    state["remaining"] = secs
    state["running"] = True
    state["paused"] = False
    state["flash"] = False
    state["started_at"] = time.time()
    save_state()


def set_timer_dialog():
    import tkinter as tk
    from tkinter import simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result = simpledialog.askstring(
        "Set Timer",
        "Duration (25, 5m, 90s, 2h) or target time (14:30):",
        parent=root,
    )
    root.destroy()
    if result:
        secs = parse_time(result)
        if secs and secs > 0:
            start_timer(secs)


def set_target_dialog():
    import tkinter as tk
    from tkinter import simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result = simpledialog.askstring(
        "Countdown to Hour",
        "Target time (e.g. 14:30, 9:00, 23:00):",
        parent=root,
    )
    root.destroy()
    if result:
        secs = parse_time(result)
        if secs and secs > 0:
            start_timer(secs)


def set_preset(minutes):
    def action(icon, item):
        start_timer(minutes * 60)
    return action


def on_set_timer(icon, item):
    threading.Thread(target=set_timer_dialog, daemon=True).start()


def on_set_target(icon, item):
    threading.Thread(target=set_target_dialog, daemon=True).start()


def on_pause_resume(icon, item):
    if state["running"]:
        state["paused"] = not state["paused"]
        save_state()


def on_reset(icon, item):
    state["running"] = False
    state["remaining"] = 0
    state["total"] = 0
    state["paused"] = False
    state["flash"] = False
    save_state()


def on_quit(icon, item):
    save_state()
    icon.stop()


def timer_loop():
    save_counter = 0
    while True:
        time.sleep(1)
        if icon_ref is None:
            continue
        if state["running"] and not state["paused"] and state["remaining"] > 0:
            state["remaining"] -= 1
            if state["remaining"] <= 0:
                state["remaining"] = 0
                state["flash"] = True
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            # Save every 30 seconds
            save_counter += 1
            if save_counter >= 30:
                save_state()
                save_counter = 0
        icon_ref.icon = render_icon()
        icon_ref.title = get_tooltip()


def pause_text(item):
    return "Resume" if state["paused"] else "Pause"


def build_menu():
    presets = pystray.Menu(
        *[pystray.MenuItem(f"{m} min", set_preset(m)) for m in [5, 10, 15, 25, 30, 45, 60, 90, 120]]
    )
    return pystray.Menu(
        pystray.MenuItem("Set Timer...", on_set_timer),
        pystray.MenuItem("Countdown to Hour...", on_set_target),
        pystray.MenuItem("Presets", presets),
        pystray.MenuItem(pause_text, on_pause_resume),
        pystray.MenuItem("Reset", on_reset),
        pystray.MenuItem("Quit", on_quit),
    )


def main():
    global icon_ref
    load_state()
    icon_ref = pystray.Icon("timer", render_icon(), get_tooltip(), build_menu())
    t = threading.Thread(target=timer_loop, daemon=True)
    t.start()
    icon_ref.run()


if __name__ == "__main__":
    main()
