"""Study Buddy floating over other apps (Windows): a small always-on-top window.

Started by Jarvis when "Float over other apps" is on (Settings). It asks Jarvis on this computer
(127.0.0.1) which pose to show, every second, and has a menu: open Jarvis, Coding Focus on/off,
snooze, pause, hide. It sends nothing anywhere else and closes when Jarvis stops.

    pythonw -m jarvis.overlay --port 8765 --data-dir <folder>    (the session token comes in an environment variable)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

KEY = "#fefffe"  # keyed-out colour: the PNGs are flattened on it (see tools/make_brand_assets.py)
ART = Path(__file__).parent / "static" / "companion"


class Overlay:
    def __init__(self, port: int, token: str, data_dir: Path):
        import tkinter as tk

        self.tk = tk
        self.base = f"http://127.0.0.1:{port}"
        self.token = token
        self.state_file = data_dir / "overlay.json"
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.label = tk.Label(self.win, bg=KEY, bd=0, cursor="hand2")
        self.label.pack()
        self.images: dict[str, object] = {}
        self.pose = ""
        self.pack_id = ""
        self.message_id = None
        self.failures = 0
        self.t0 = time.time()
        self.hop_until = 0.0
        self.blink_at = 0.0
        self.shake_until = 0.0
        self.base_xy = self._load_position()
        self.drag = None
        self.bubble = None
        self.bubble_until = 0.0
        self.focus = {}
        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._motion)
        self.label.bind("<ButtonRelease-1>", self._release)
        self.label.bind("<Button-3>", lambda e: self._menu(e))
        self.win.geometry(f"+{self.base_xy[0]}+{self.base_xy[1]}")

    # ---------------------------------------------------------------- talking to Jarvis
    def call(self, path: str, method: str = "GET", body: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method, headers={"X-Jarvis-Token": self.token,
                                     "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read() or b"null")

    def poll(self) -> None:
        try:
            st = self.call("/api/companion/state")
            self.failures = 0
        except Exception:
            self.failures += 1
            if self.failures > 30:  # Jarvis is gone: close quietly
                self.root.destroy()
                return
            self.root.after(1000, self.poll)
            return
        if not st.get("overlay"):
            self.root.destroy()
            return
        self.focus = st.get("focus") or {}
        self.set_pose(st["pack"], st["pose"])
        msg = st.get("message")
        if msg and msg.get("id") != self.message_id:
            self.message_id = msg["id"]
            self.say(msg["text"], 12)
            if msg.get("alert") and sys.platform == "win32":
                try:
                    import winsound
                    winsound.MessageBeep(0x40)  # a soft system "asterisk" sound, once per reminder
                except Exception:
                    pass
        self.root.after(1000, self.poll)

    # ---------------------------------------------------------------- drawing
    def image(self, pack: str, pose: str, closed: bool = False):
        """Her picture for a pose; `closed` is the same picture with her eyes shut (for blinking), or None."""
        key = f"{pack}/{pose}/{closed}"
        if key not in self.images:
            packs = json.loads((ART / "packs.json").read_text(encoding="utf-8"))["packs"]
            p = next((x for x in packs if x["id"] == pack), packs[0])
            fallback = {"relax": "sleepy", "care": "cheer"}.get(pose, "study")
            item = next((i for i in p["items"] if i["mood"] == pose), None) or next((i for i in p["items"] if i["mood"] == fallback), p["items"][0])
            name = item.get("overlay_blink") if closed else item["overlay"]
            self.images[key] = self.tk.PhotoImage(master=self.root, file=str(ART / name)) if name else None
        return self.images[key]

    def set_pose(self, pack: str, pose: str) -> None:
        if (pack, pose) == (self.pack_id, self.pose):
            return
        changed = bool(self.pose)
        self.pack_id, self.pose = pack, pose
        self.label.configure(image=self.image(pack, pose))
        self.blink_at = time.time() + 2 + random.random() * 3
        if changed:
            self.hop_until = time.time() + 0.45  # a little hop when her expression changes
        if pose == "pouty":
            self.shake_until = time.time() + 0.9

    def animate(self) -> None:
        now = time.time()
        if self.pose and now >= self.blink_at:  # blink: eyes shut for a moment, every few seconds
            shut = self.image(self.pack_id, self.pose, closed=True)
            if shut is not None and now < self.blink_at + 0.15:
                self.label.configure(image=shut)
            else:
                self.label.configure(image=self.image(self.pack_id, self.pose))
                if now >= self.blink_at + 0.15 or shut is None:
                    self.blink_at = now + 2.5 + random.random() * 4
        if not self.drag:
            x, y = self.base_xy
            dy = math.sin((now - self.t0) * 2.1) * 3  # breathing bob
            dx = 0
            if now < self.hop_until:
                k = 1 - (self.hop_until - now) / 0.45
                dy -= math.sin(k * math.pi) * 16
            if now < self.shake_until:
                dx = math.sin(now * 60) * 4
            self.win.geometry(f"+{int(x + dx)}+{int(y + dy)}")
        if self.bubble and now > self.bubble_until:
            self.bubble.destroy()
            self.bubble = None
        elif self.bubble:
            self._place_bubble()
        self.root.after(40, self.animate)

    def say(self, text: str, seconds: float = 8) -> None:
        tk = self.tk
        if self.bubble:
            self.bubble.destroy()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.configure(bg="#ffffff", highlightthickness=1, highlightbackground="#c9ced6")
        tk.Label(b, text=text, bg="#ffffff", fg="#1c2330", wraplength=240, justify="left",
                 font=("Segoe UI", 10), padx=10, pady=8).pack()
        b.bind("<Button-1>", lambda e: (b.destroy(), setattr(self, "bubble", None)))
        self.bubble = b
        self.bubble_until = time.time() + seconds
        self._place_bubble()

    def _place_bubble(self) -> None:
        self.bubble.update_idletasks()
        bw, bh = self.bubble.winfo_width(), self.bubble.winfo_height()
        x = self.win.winfo_x() + self.win.winfo_width() // 2 - bw // 2
        y = self.win.winfo_y() - bh - 6
        if y < 0:
            y = self.win.winfo_y() + self.win.winfo_height() + 6
        x = max(0, min(x, self.root.winfo_screenwidth() - bw))
        self.bubble.geometry(f"+{x}+{y}")

    # ---------------------------------------------------------------- mouse
    def _press(self, e) -> None:
        self.drag = (e.x_root, e.y_root, self.base_xy[0], self.base_xy[1], False)

    def _motion(self, e) -> None:
        if not self.drag:
            return
        sx, sy, bx, by, moved = self.drag
        dx, dy = e.x_root - sx, e.y_root - sy
        if moved or abs(dx) + abs(dy) > 5:
            self.drag = (sx, sy, bx, by, True)
            self.base_xy = (bx + dx, by + dy)
            self.win.geometry(f"+{bx + dx}+{by + dy}")

    def _release(self, e) -> None:
        moved = self.drag[4] if self.drag else False
        self.drag = None
        if moved:
            self._save_position()
        else:
            self._menu(e)

    def _menu(self, e) -> None:
        tk = self.tk
        m = tk.Menu(self.root, tearoff=0)
        f = self.focus
        m.add_command(label="Open Jarvis", command=lambda: webbrowser.open(self.base + "/"))
        m.add_separator()
        on = f.get("enabled")
        m.add_command(label="Turn Coding Focus off" if on else "Turn Coding Focus on",
                      command=lambda: self._do("/api/focus", "PUT", {"focus_enabled": not on}))
        if on:
            m.add_command(label="Snooze 15 minutes", command=lambda: self._do("/api/focus/snooze", "POST", {"minutes": 15}))
            waiting = f.get("paused") or f.get("snoozed_for")
            m.add_command(label="Resume" if waiting else "Pause",
                          command=lambda: self._do("/api/focus/resume" if waiting else "/api/focus/pause", "POST", {}))
        m.add_command(label="Take a 5-minute break", command=lambda: self._do("/api/focus/snooze", "POST", {"minutes": 5, "break": True}))
        m.add_separator()
        m.add_command(label="Hide Study Buddy", command=lambda: self._do("/api/companion/overlay", "PUT", {"enabled": False}))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _do(self, path: str, method: str, body: dict) -> None:
        try:
            self.call(path, method, body)
        except Exception as exc:
            self.say(f"Couldn't reach Jarvis: {exc}", 5)

    # ---------------------------------------------------------------- position
    def _load_position(self) -> tuple[int, int]:
        try:
            x, y = json.loads(self.state_file.read_text(encoding="utf-8"))["pos"]
            if 0 <= x < self.root.winfo_screenwidth() - 40 and 0 <= y < self.root.winfo_screenheight() - 40:
                return int(x), int(y)
        except Exception:
            pass
        return self.root.winfo_screenwidth() - 220, self.root.winfo_screenheight() - 300

    def _save_position(self) -> None:
        try:
            self.state_file.write_text(json.dumps({"pos": list(self.base_xy)}), encoding="utf-8")
        except OSError:
            pass

    def run(self) -> None:
        self.root.after(50, self.poll)
        self.root.after(80, self.animate)
        self.root.mainloop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()
    token = os.environ.get("JARVIS_OVERLAY_TOKEN", "")
    if not token:
        raise SystemExit("Started without a session token.")
    Overlay(args.port, token, Path(args.data_dir)).run()


if __name__ == "__main__":
    main()
