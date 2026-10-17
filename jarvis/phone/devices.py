"""Pairing phones with this computer.

1. On the computer you click "Pair a phone"; Jarvis shows a 6-digit code that
   works once, for 5 minutes, with at most 5 wrong guesses.
2. The phone sends the code and receives a long random device token, which it
   keeps. Jarvis stores only a hash of the token.
3. Every request from the phone must carry that token. Removing the phone on
   the computer revokes it immediately.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from ..activity import ActivityLog
from ..db import Database, now_iso

CODE_TTL_SECONDS = 300
CODE_MAX_ATTEMPTS = 5
PAIR_RATE_LIMIT = 10  # attempts per client address per 10 minutes


class PairingError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceRegistry:
    def __init__(self, db: Database, activity: ActivityLog):
        self.db = db
        self.activity = activity
        self._lock = threading.Lock()
        self._code: dict | None = None
        self._attempts: dict[str, deque] = defaultdict(deque)
        self._seen_written: dict[int, float] = {}

    # ---- pairing codes (shown on the computer)
    def new_code(self) -> dict:
        with self._lock:
            self._code = {"code": f"{secrets.randbelow(10**6):06d}",
                          "expires": time.time() + CODE_TTL_SECONDS, "attempts": 0}
            return self._code_info()

    def cancel_code(self) -> None:
        with self._lock:
            self._code = None

    def _code_info(self) -> dict | None:
        c = self._code
        if not c or c["expires"] < time.time() or c["attempts"] >= CODE_MAX_ATTEMPTS:
            return None
        return {"code": c["code"], "seconds_left": int(c["expires"] - time.time())}

    def code_info(self) -> dict | None:
        with self._lock:
            return self._code_info()

    # ---- pairing (called by the phone)
    def pair(self, code: str, name: str, client: str) -> tuple[dict, str]:
        now = time.time()
        with self._lock:
            recent = self._attempts[client]
            while recent and recent[0] < now - 600:
                recent.popleft()
            if len(recent) >= PAIR_RATE_LIMIT:
                raise PairingError("Too many pairing attempts. Wait a few minutes and try again.", 429)
            recent.append(now)
            c = self._code
            if not c or c["expires"] < now or c["attempts"] >= CODE_MAX_ATTEMPTS:
                raise PairingError("There is no active pairing code. On your computer, open Jarvis → "
                                   "Settings → Phone access and click \"Pair a phone\".")
            if not secrets.compare_digest(str(code).strip(), c["code"]):
                c["attempts"] += 1
                left = CODE_MAX_ATTEMPTS - c["attempts"]
                if left <= 0:
                    self._code = None
                    raise PairingError("Wrong code too many times. Create a new code on your computer.")
                raise PairingError(f"That code isn't right. {left} attempt{'s' if left != 1 else ''} left.")
            self._code = None  # one use only
        token = secrets.token_urlsafe(32)
        clean = " ".join(str(name or "").split())[:60] or "Phone"
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO devices (name, token_hash, created_at, last_seen) VALUES (?, ?, ?, ?)",
                               (clean, _hash(token), now_iso(), now_iso()))
            device_id = cur.lastrowid
        self.activity.record("phone_paired", f"Paired phone '{clean}'", device_id=device_id, address=client)
        return self.get(device_id), token

    def issue(self, name: str) -> tuple[dict, str]:
        """Create a device key directly. Only for the Jarvis app on the same phone as a pocket
        Jarvis, which asks for it through Termux (no pairing code needed)."""
        token = secrets.token_urlsafe(32)
        clean = " ".join(str(name or "").split())[:60] or "Phone"
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO devices (name, token_hash, created_at, last_seen) VALUES (?, ?, ?, ?)",
                               (clean, _hash(token), now_iso(), now_iso()))
            device_id = cur.lastrowid
        self.activity.record("phone_paired", f"Paired '{clean}' on this phone", device_id=device_id)
        return self.get(device_id), token

    # ---- devices
    def verify(self, token: str) -> dict | None:
        if not token:
            return None
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM devices WHERE token_hash = ? AND revoked_at IS NULL",
                               (_hash(token),)).fetchone()
            if not row:
                return None
            if time.time() - self._seen_written.get(row["id"], 0) > 60:
                conn.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (now_iso(), row["id"]))
                self._seen_written[row["id"]] = time.time()
        return {k: row[k] for k in ("id", "name", "created_at", "last_seen")}

    def get(self, device_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT id, name, created_at, last_seen, revoked_at FROM devices WHERE id = ?",
                               (device_id,)).fetchone()
        if not row:
            raise PairingError(f"Phone #{device_id} is not paired.", 404)
        return dict(row)

    def list(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT id, name, created_at, last_seen FROM devices WHERE revoked_at IS NULL "
                                "ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def revoke(self, device_id: int, by_phone: bool = False) -> None:
        device = self.get(device_id)
        with self.db.connect() as conn:
            conn.execute("UPDATE devices SET revoked_at = ? WHERE id = ?", (now_iso(), device_id))
        who = "the phone itself" if by_phone else "you"
        self.activity.record("phone_removed", f"Removed phone '{device['name']}' (by {who})", device_id=device_id)
