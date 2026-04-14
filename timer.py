import math
import subprocess
import sys
import threading
import time
import json
import re
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import pystray
from PIL import Image, ImageDraw, ImageFont

SIZE = 64
APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
STATE_FILE = APP_DIR / "timer_state.json"
CHECKIN_INTERVAL = 900  # 15 minutes
CHECKIN_LOG = APP_DIR / "checkins.jsonl"
SCREENSHOT_DIR = APP_DIR / "screenshots"

state = {
    "total": 0,
    "remaining": 0,
    "paused": False,
    "running": False,
    "flash": False,
    "started_at": 0,
    "checkins_enabled": True,
    "urgency_mode": "relative",  # "relative" = ratio-based, "absolute" = fixed window
    "urgency_window": 120,       # absolute mode: total window in minutes (color maps over this)
}
checkin_dialog_open = False
icon_ref = None


def save_state():
    try:
        data = {
            "total": state["total"],
            "remaining": state["remaining"],
            "paused": state["paused"],
            "running": state["running"],
            "started_at": state["started_at"],
            "checkins_enabled": state["checkins_enabled"],
            "urgency_mode": state["urgency_mode"],
            "urgency_window": state["urgency_window"],
            "saved_at": time.time(),
        }
        STATE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


def load_state():
    try:
        if not STATE_FILE.exists():
            return
        data = json.loads(STATE_FILE.read_text())
        if not data.get("running"):
            return
        elapsed_while_closed = time.time() - data.get("saved_at", time.time())
        if data.get("paused"):
            state["total"] = data["total"]
            state["remaining"] = data["remaining"]
            state["paused"] = True
            state["running"] = True
            state["started_at"] = data.get("started_at", 0)
        else:
            remaining = data["remaining"] - int(elapsed_while_closed)
            if remaining > 0:
                state["total"] = data["total"]
                state["remaining"] = remaining
                state["running"] = True
                state["paused"] = False
                state["started_at"] = data.get("started_at", 0)
            else:
                state["total"] = data["total"]
                state["remaining"] = 0
                state["running"] = True
                state["flash"] = True
                state["started_at"] = data.get("started_at", 0)
                notify("Timer expired while closed!")
        state["checkins_enabled"] = data.get("checkins_enabled", True)
        state["urgency_mode"] = data.get("urgency_mode", "relative")
        state["urgency_window"] = data.get("urgency_window", 120)
    except Exception:
        pass


def notify(message="Timer finished!"):
    """Play a notification sound and show a desktop notification."""
    try:
        subprocess.Popen(
            ["notify-send", "-u", "critical", "Tray Timer", message],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass
    # Try common sound players
    for cmd in [
        ["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
        ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
        ["aplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"],
        ["canberra-gtk-play", "-i", "alarm-clock-elapsed"],
    ]:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
        except FileNotFoundError:
            continue


def capture_screenshot():
    """Grab desktop screenshot. Returns PIL Image or None."""
    try:
        import mss
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        pass
    # Fallback to scrot
    try:
        tmp = "/tmp/traytimer_checkin.png"
        subprocess.run(["scrot", tmp], check=True, capture_output=True, timeout=5)
        img = Image.open(tmp)
        img.load()
        os.unlink(tmp)
        return img
    except Exception:
        return None


def _find_font(size):
    """Find a suitable bold sans-serif font on Linux."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    # Last resort: try fc-match
    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", "monospace:bold"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return ImageFont.truetype(result.stdout.strip(), size)
    except Exception:
        pass
    return ImageFont.load_default()


def render_icon():
    S = SIZE * 2  # 2x supersample
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, S // 2
    pad = 2
    r = S // 6

    from PIL import ImageFilter

    # --- Bezel (dark outer frame) ---
    bezel_r = S // 5
    draw.rounded_rectangle([pad, pad, S - pad, S - pad], radius=bezel_r,
                           fill=(50, 48, 47))  # gruvbox bg0_s

    # Bezel highlight on top edge
    draw.rounded_rectangle([pad, pad, S - pad, pad + S // 8], radius=bezel_r,
                           fill=(65, 60, 56))

    # --- Screen area (inset) ---
    scr = S // 7  # screen inset from edge
    scr_r = S // 7  # screen corner radius (rounder, like a CRT)

    if state["running"] or state["remaining"] > 0:
        secs_left = max(0, state["remaining"])

        # Urgency: either ratio-based or absolute-time-based
        if state["urgency_mode"] == "absolute":
            window_secs = state["urgency_window"] * 60
            urgency = max(0.0, min(1.0, 1.0 - secs_left / max(window_secs, 1)))
        else:
            ratio = secs_left / max(state["total"], 1)
            urgency = 1.0 - ratio  # 0.0 = full, 1.0 = empty

        # Screen color: lerp teal → amber → red based on urgency
        if state["flash"]:
            pulse = (math.sin(time.time() * 5) + 1) / 2
            sr = int(140 + 80 * pulse)
            sg = int(30 + 20 * pulse)
            sb = int(20 + 15 * pulse)
        else:
            if urgency < 0.5:
                t = urgency * 2  # 0→1 over first half
                sr = int(69 + (150 - 69) * t)
                sg = int(133 + (120 - 133) * t)
                sb = int(136 + (50 - 136) * t)
            else:
                t = (urgency - 0.5) * 2  # 0→1 over second half
                sr = int(150 + (180 - 150) * t)
                sg = int(120 + (40 - 120) * t)
                sb = int(50 + (30 - 50) * t)
        screen_color = (sr, sg, sb)

        secs = max(0, state["remaining"])
        mins = (secs + 59) // 60
        if mins > 9:
            text = str(min(9, (mins + 30) // 60)) or "0"
        elif mins > 0:
            text = str(mins)
        else:
            text = str(max(secs, 0))

    elif state["paused"]:
        screen_color = (69, 133, 136)
        text = "||"
    else:
        screen_color = (40, 40, 38)
        text = "--"

    # Screen background
    draw.rounded_rectangle([scr, scr, S - scr, S - scr], radius=scr_r,
                           fill=screen_color)

    # Screen glow — lighter center, darker edges (CRT bloom)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    # Bright center spot
    inner = scr + S // 8
    gd.rounded_rectangle([inner, inner, S - inner, S - inner], radius=scr_r // 2,
                         fill=(255, 255, 255, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=S // 8))
    img = Image.alpha_composite(img, glow)

    # Screen edge darkening (vignette)
    vig = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vig)
    vd.rounded_rectangle([scr, scr, S - scr, S - scr], radius=scr_r,
                         outline=(0, 0, 0, 80), width=S // 10)
    vig = vig.filter(ImageFilter.GaussianBlur(radius=S // 10))
    img = Image.alpha_composite(img, vig)
    draw = ImageDraw.Draw(img)

    # --- Number (phosphor text) ---
    # Much brighter phosphor text — needs to pop against screen
    fg = (min(255, screen_color[0] + 130),
          min(255, screen_color[1] + 130),
          min(255, screen_color[2] + 130))

    font = _find_font(S * 65 // 128)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = cx - tw // 2 - bbox[0]
    y = cy - th // 2 - bbox[1]

    # Text glow (phosphor bloom)
    tg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tgd = ImageDraw.Draw(tg)
    tgd.text((x, y), text, fill=(*fg, 100), font=font)
    tg = tg.filter(ImageFilter.GaussianBlur(radius=3))
    img = Image.alpha_composite(img, tg)
    draw = ImageDraw.Draw(img)

    # Sharp text
    draw.text((x, y), text, fill=fg, font=font)

    # --- Scanlines (subtle) ---
    for sy in range(scr, S - scr, 3):
        draw.line([(scr, sy), (S - scr, sy)], fill=(0, 0, 0, 20))

    # Final clip to bezel shape
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([pad, pad, S - pad, S - pad], radius=bezel_r, fill=255)
    img.putalpha(mask)

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
    return "Tray Timer"


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


def _gtk_input_dialog(title, label_text, placeholder=""):
    """Native GTK input dialog. Runs on the GTK main loop thread. Returns string or None."""
    result = {"value": None}
    done = threading.Event()

    def run():
        dialog = Gtk.Dialog(title=title, transient_for=None, modal=True)
        dialog.set_keep_above(True)
        dialog.set_resizable(False)
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(12)
        box.set_margin_bottom(4)

        label = Gtk.Label(label=label_text)
        label.set_xalign(0)
        box.add(label)

        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        entry.set_activates_default(True)
        box.add(entry)

        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            result["value"] = entry.get_text().strip()
        dialog.destroy()
        # Drain pending GTK events so the window fully closes
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        done.set()

    GLib.idle_add(run)
    done.wait()
    return result["value"]


def set_timer_dialog():
    val = _gtk_input_dialog(
        "Set Timer",
        "Duration or target time:",
        "e.g. 25, 5m, 90s, 2h, 14:30")
    if val:
        secs = parse_time(val)
        if secs and secs > 0:
            start_timer(secs)


def set_target_dialog():
    val = _gtk_input_dialog(
        "Countdown to Hour",
        "Target time:",
        "e.g. 14:30, 9:00, 23:00")
    if val:
        secs = parse_time(val)
        if secs and secs > 0:
            start_timer(secs)


def save_screenshot(img, ts_iso):
    if img is None:
        return None
    try:
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        stamp = ts_iso.replace(":", "-").replace("T", "_")
        fname = f"checkin_{stamp}.jpg"
        path = SCREENSHOT_DIR / fname
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(path, "JPEG", quality=85, optimize=True)
        return f"screenshots/{fname}"
    except Exception:
        return None


def checkin_dialog():
    global checkin_dialog_open
    checkin_dialog_open = True
    try:
        shot = capture_screenshot()

        result = {"text": None, "screenshot": True}
        done = threading.Event()

        def run():
            dialog = Gtk.Dialog(title="Check-in", transient_for=None, modal=True)
            dialog.set_keep_above(True)
            dialog.set_resizable(False)
            dialog.add_buttons(
                "Skip", Gtk.ResponseType.CANCEL,
                "Log", Gtk.ResponseType.OK,
            )
            dialog.set_default_response(Gtk.ResponseType.OK)

            box = dialog.get_content_area()
            box.set_spacing(8)
            box.set_margin_start(16)
            box.set_margin_end(16)
            box.set_margin_top(12)
            box.set_margin_bottom(4)

            label = Gtk.Label(label="What are you working on?")
            label.set_xalign(0)
            box.add(label)

            entry = Gtk.Entry()
            entry.set_placeholder_text("1-2 words")
            entry.set_activates_default(True)
            box.add(entry)

            check = Gtk.CheckButton(label="Include screenshot")
            check.set_active(True)
            box.add(check)

            dialog.show_all()

            # Center on primary monitor
            display = Gdk.Display.get_default()
            monitor = display.get_monitor(0) or display.get_primary_monitor()
            if monitor:
                geom = monitor.get_geometry()
                dialog.get_window().process_updates(True)
                w, h = dialog.get_size()
                x = geom.x + (geom.width - w) // 2
                y = geom.y + (geom.height - h) // 2
                dialog.move(x, y)

            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                result["text"] = entry.get_text().strip()
                result["screenshot"] = check.get_active()
            dialog.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            done.set()

        GLib.idle_add(run)
        done.wait()

        if result["text"]:
            ts = datetime.now().isoformat(timespec="seconds")
            screenshot_path = save_screenshot(shot, ts) if result["screenshot"] else None
            entry_record = {
                "time": ts,
                "elapsed": int(time.time() - state["started_at"]) if state["started_at"] else 0,
                "remaining": state["remaining"],
                "note": result["text"],
                "screenshot": screenshot_path,
            }
            with open(CHECKIN_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry_record) + "\n")
            shutil.copy2(CHECKIN_LOG, str(CHECKIN_LOG) + ".bak")
    finally:
        checkin_dialog_open = False


def view_checkins_window():
    if not CHECKIN_LOG.exists():
        entries = []
    else:
        entries = []
        for line in CHECKIN_LOG.read_text(encoding="utf-8").strip().splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    done = threading.Event()

    def run():
        win = Gtk.Window(title="Check-ins")
        win.set_default_size(380, 420)
        win.set_keep_above(True)
        win.connect("destroy", lambda w: done.set())

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        win.add(scroll)

        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_cursor_visible(False)
        textview.set_wrap_mode(Gtk.WrapMode.WORD)
        textview.set_left_margin(14)
        textview.set_right_margin(14)
        textview.set_top_margin(14)
        textview.set_bottom_margin(14)
        scroll.add(textview)

        buf = textview.get_buffer()
        bold_tag = buf.create_tag("bold", weight=700)
        dim_tag = buf.create_tag("dim", foreground_rgba=None)
        # Use dim style via scale
        dim_tag.set_property("scale", 0.9)

        if not entries:
            buf.insert(buf.get_end_iter(), "No check-ins yet.")
        else:
            current_date = None
            for e in entries:
                t = e.get("time", "")
                date_part = t[:10]
                time_part = t[11:16]
                if date_part != current_date:
                    if current_date is not None:
                        buf.insert(buf.get_end_iter(), "\n")
                    buf.insert_with_tags(buf.get_end_iter(), f"  {date_part}\n", bold_tag)
                    current_date = date_part
                buf.insert(buf.get_end_iter(), f"  {time_part}  {e.get('note', '')}\n")

        win.show_all()

    GLib.idle_add(run)
    done.wait()


def on_view_checkins(icon, item):
    threading.Thread(target=view_checkins_window, daemon=True).start()


def on_toggle_checkins(icon, item):
    state["checkins_enabled"] = not state["checkins_enabled"]
    save_state()


def _fmt_window():
    m = state["urgency_window"]
    if m >= 60:
        h = m / 60
        return f"{h:.0f}h" if h == int(h) else f"{h:.1f}h"
    return f"{m:.0f}m"


def on_set_urgency_relative(icon, item):
    state["urgency_mode"] = "relative"
    save_state()


def on_set_urgency_window(icon, item):
    def do():
        val = _gtk_input_dialog(
            "Urgency Window",
            "Full color range maps over this duration:",
            "e.g. 2h, 30m, 90, 18h")
        if val:
            secs = parse_time(val)
            if secs and secs > 0:
                state["urgency_mode"] = "absolute"
                state["urgency_window"] = secs / 60
                save_state()
    threading.Thread(target=do, daemon=True).start()


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
    checkin_counter = 0
    while True:
        time.sleep(1)
        if icon_ref is None:
            continue
        if state["running"] and not state["paused"] and state["remaining"] > 0:
            state["remaining"] -= 1
            if state["remaining"] <= 0:
                state["remaining"] = 0
                state["flash"] = True
                notify()
            save_counter += 1
            if save_counter >= 30:
                save_state()
                save_counter = 0
            if state["checkins_enabled"] and not checkin_dialog_open:
                checkin_counter += 1
                if checkin_counter >= CHECKIN_INTERVAL:
                    checkin_counter = 0
                    threading.Thread(target=checkin_dialog, daemon=True).start()
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
        pystray.MenuItem("View Check-ins", on_view_checkins),
        pystray.MenuItem(
            lambda item: "Disable Check-ins" if state["checkins_enabled"] else "Enable Check-ins",
            on_toggle_checkins,
        ),
        pystray.MenuItem("Urgency", pystray.Menu(
            pystray.MenuItem(
                lambda item: "● Relative (% of timer)" if state["urgency_mode"] == "relative" else "  Relative (% of timer)",
                on_set_urgency_relative,
            ),
            pystray.MenuItem(
                lambda item: f"● Absolute ({_fmt_window()})" if state["urgency_mode"] == "absolute" else f"  Absolute ({_fmt_window()})",
                on_set_urgency_window,
            ),
        )),
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
