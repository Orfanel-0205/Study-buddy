"""Coding Focus: notices when you've been away from your coding apps for too long.

Privacy: on Windows it asks the system only for the *program name* of the window in front (for
example "Code.exe"), every few seconds. It never reads keystrokes, window titles, screen contents
or your code, and it does nothing unless you turn Coding Focus on. On other systems (and on the
phone) it isn't available here; the phone app has its own timer.

States: off, coding, away (within the grace period), distracted (past it), snoozed, paused.
A reminder is raised once per stretch away, and never more often than the cooldown.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import date

from .config import ConfigStore
from .db import Database, now_iso

log = logging.getLogger(__name__)

BROWSERS = {"msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"}
NEUTRAL = {"pythonw.exe", "python.exe", "explorer.exe", "searchhost.exe", "startmenuexperiencehost.exe",
           "shellexperiencehost.exe", "lockapp.exe", ""}  # Study Buddy's own window, the taskbar, the lock screen
POLL_SECONDS = 3.0
MESSAGES = [
    "Hmph! You've been away from coding for {m} min. Come back and finish one small thing? \U0001F624",
    "Hey! {m} min away already. Your code misses you. \U0001F4A2",
    "Back to coding? Just 10 more minutes, then a proper break. \U0001F624",
]


def foreground_app() -> str | None:
    """The executable name of the foreground window (lower case), or None if this system can't tell."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)


class FocusMonitor:
    def __init__(self, config: ConfigStore, db: Database, probe=foreground_app, clock=time.time):
        self.config = config
        self.db = db
        self.probe = probe
        self.clock = clock
        self.supported = probe() is not None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.app = ""
        self.state = "off"
        self.away_since: float | None = None
        self.snooze_until = 0.0
        self.paused = False
        self.last_alert_at = 0.0
        self.alerted_this_stretch = False
        self.alert: dict | None = None
        self.alert_seq = 0
        self.heartbeat_at = 0.0  # the Jarvis page reports when it's the focused tab (it counts as studying)
        self.seen: dict[str, float] = {}
        self._unsaved_coding = 0.0
        self._last_tick = clock()

    # ---------------------------------------------------------------- control
    def start(self) -> None:
        if not self.supported or self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="jarvis-focus", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._save_coding()

    def snooze(self, minutes: int) -> None:
        with self._lock:
            self.snooze_until = self.clock() + max(1, min(minutes, 240)) * 60
            self.away_since = None
            self.alerted_this_stretch = False

    def pause(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused
            if not paused:
                self.snooze_until = 0.0  # Resume means "watch again now", also after a snooze or break
            self.away_since = None
            self.alerted_this_stretch = False

    def heartbeat(self) -> None:
        self.heartbeat_at = self.clock()

    def _run(self) -> None:
        while not self._stop.wait(POLL_SECONDS):
            try:
                self.tick()
            except Exception:  # never let a probe problem stop the server
                log.exception("Coding Focus check failed")

    # ---------------------------------------------------------------- the state machine
    def tick(self, app: str | None = None) -> None:
        s = self.config.get()
        now = self.clock()
        dt = min(now - self._last_tick, 30.0)
        self._last_tick = now
        app = (self.probe() if app is None else app) or ""
        with self._lock:
            if app not in NEUTRAL:
                self.app = app
                self.seen[app] = now
            current = self.app
            coding_apps = {a.lower() for a in s.focus_apps}
            in_jarvis = current in BROWSERS and now - self.heartbeat_at < 10
            coding = current in coding_apps or in_jarvis
            if not s.focus_enabled:
                self.state, self.away_since, self.alerted_this_stretch = "off", None, False
            elif self.paused:
                self.state = "paused"
            elif now < self.snooze_until:
                self.state = "snoozed"
            elif coding:
                self.state, self.away_since, self.alerted_this_stretch = "coding", None, False
                self._unsaved_coding += dt
            else:
                if self.away_since is None:
                    self.away_since = now
                away = now - self.away_since
                if away >= s.focus_grace_minutes * 60:
                    self.state = "distracted"
                    if not self.alerted_this_stretch and now - self.last_alert_at >= s.focus_cooldown_minutes * 60:
                        self.alerted_this_stretch = True
                        self.last_alert_at = now
                        self.alert_seq += 1
                        minutes = int(away // 60)
                        self.alert = {"id": self.alert_seq, "at": now_iso(), "minutes": minutes,
                                      "message": MESSAGES[self.alert_seq % len(MESSAGES)].format(m=minutes)}
                        self._count_alert()
                else:
                    self.state = "away"
        if self._unsaved_coding >= 60:
            self._save_coding()

    def status(self) -> dict:
        s = self.config.get()
        now = self.clock()
        with self._lock:
            away = int(now - self.away_since) if self.away_since else 0
            return {"supported": self.supported, "enabled": s.focus_enabled, "state": self.state, "app": self.app,
                    "away_seconds": away, "grace_seconds": s.focus_grace_minutes * 60,
                    "cooldown_minutes": s.focus_cooldown_minutes, "grace_minutes": s.focus_grace_minutes,
                    "snoozed_for": max(0, int(self.snooze_until - now)), "paused": self.paused,
                    "alert": self.alert, "apps": s.focus_apps, "overlay": s.overlay_enabled,
                    "coding_minutes_today": self.coding_minutes_today()}

    def recent_apps(self) -> list[str]:
        with self._lock:
            return [a for a, _ in sorted(self.seen.items(), key=lambda kv: -kv[1])][:20]

    # ---------------------------------------------------------------- daily totals (for Progress)
    def _save_coding(self) -> None:
        seconds = int(self._unsaved_coding)
        if seconds <= 0:
            return
        self._unsaved_coding -= seconds
        with self.db.connect() as conn:
            conn.execute("INSERT INTO focus_days (day, coding_seconds, updated_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(day) DO UPDATE SET coding_seconds = coding_seconds + excluded.coding_seconds, "
                         "updated_at = excluded.updated_at", (date.today().isoformat(), seconds, now_iso()))

    def _count_alert(self) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO focus_days (day, alerts, updated_at) VALUES (?, 1, ?) "
                         "ON CONFLICT(day) DO UPDATE SET alerts = alerts + 1, updated_at = excluded.updated_at",
                         (date.today().isoformat(), now_iso()))

    def coding_minutes_today(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT coding_seconds FROM focus_days WHERE day = ?", (date.today().isoformat(),)).fetchone()
        return int(((row["coding_seconds"] if row else 0) + self._unsaved_coding) // 60)
