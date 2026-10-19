"""Phone access: the mobile app connects to Jarvis on this computer over your home Wi-Fi.

What the phone may do is an explicit allow-list. File changes, commands,
settings and opening projects stay on the computer.
"""

from __future__ import annotations

import re

from .devices import DeviceRegistry, PairingError
from .listener import PHONE_CHANNEL, PhoneChannel, PhoneListener

# (method, path) pairs a paired phone may call.
PHONE_API = [(m, re.compile(p + r"$")) for m, p in [
    ("GET", r"/api/status"),
    ("GET", r"/api/project"),
    ("GET", r"/api/conversations"),
    ("GET", r"/api/conversations/\d+"),
    ("PATCH", r"/api/conversations/\d+"),
    ("DELETE", r"/api/conversations/\d+"),
    ("POST", r"/api/chat"),
    ("POST", r"/api/chat/cancel"),
    ("GET", r"/api/tasks"),
    ("GET", r"/api/tasks/projects"),
    ("POST", r"/api/tasks"),
    ("PATCH", r"/api/tasks/\d+"),
    ("DELETE", r"/api/tasks/\d+"),
    ("POST", r"/api/tasks/\d+/breakdown"),
    ("POST", r"/api/tasks/\d+/subtasks"),
    ("POST", r"/api/tasks/plan"),
    ("GET", r"/api/images/[0-9a-f]{64}\.(jpg|png|gif|webp)"),
    ("GET", r"/api/study/decks"),
    ("POST", r"/api/study/decks"),
    ("PATCH", r"/api/study/decks/\d+"),
    ("DELETE", r"/api/study/decks/\d+"),
    ("GET", r"/api/study/decks/\d+/cards"),
    ("POST", r"/api/study/decks/\d+/cards"),
    ("PATCH", r"/api/study/cards/\d+"),
    ("DELETE", r"/api/study/cards/\d+"),
    ("GET", r"/api/study/due"),
    ("POST", r"/api/study/cards/\d+/review"),
    ("POST", r"/api/study/generate"),
    ("POST", r"/api/sync"),
    ("POST", r"/api/sync/now"),
    ("GET", r"/api/sync/status"),
    ("GET", r"/api/phone/whoami"),
    ("POST", r"/api/phone/unpair"),
    ("GET", r"/api/learn/guides"),
    ("GET", r"/api/learn/guides/[a-z0-9-]+"),
    ("GET", r"/api/learn/search"),
    ("GET", r"/api/learn/decks"),
    ("POST", r"/api/learn/decks/[a-z0-9-]+/install"),
    ("GET", r"/api/learn/exercises"),
    ("GET", r"/api/learn/exercises/[a-z0-9-]+"),
    ("PUT", r"/api/learn/exercises/[a-z0-9-]+/code"),
    ("POST", r"/api/learn/exercises/[a-z0-9-]+/hint"),
    ("GET", r"/api/learn/exercises/[a-z0-9-]+/solution"),
    ("GET", r"/api/learn/standup"),
    ("GET", r"/api/progress"),
    ("GET", r"/api/motivation"),
    ("GET", r"/api/checkins"),
    ("GET", r"/api/checkins/latest"),
    ("POST", r"/api/checkins"),
    ("GET", r"/api/checkins/insights"),
    ("GET", r"/api/build/catalog"),
    ("GET", r"/api/offline/pack"),
    ("POST", r"/api/build/plan"),
    ("POST", r"/api/build/hackathon"),
]]

# Only for Jarvis running on the phone itself (pocket mode): running practice code happens on the
# phone, never on the laptop from a phone.
POCKET_ONLY_API = [(m, re.compile(p + r"$")) for m, p in [
    ("POST", r"/api/learn/exercises/[a-z0-9-]+/run"),
    ("POST", r"/api/learn/runtimes/refresh"),
    ("GET", r"/api/pocket/model"),  # Jarvis on the phone has no laptop to change its settings from
    ("PUT", r"/api/pocket/model"),
]]

# Pages and assets the phone may load before pairing (nothing secret in them).
PHONE_PAGES = re.compile(r"^/m/?$|^/m/(manifest\.webmanifest|sw\.js|jarvis-ca\.crt)$|^/static/")


def phone_may_call(method: str, path: str, pocket: bool = False) -> bool:
    rules = PHONE_API + POCKET_ONLY_API if pocket else PHONE_API
    return any(m == method and p.match(path) for m, p in rules)


__all__ = ["DeviceRegistry", "PairingError", "PhoneChannel", "PhoneListener", "PHONE_CHANNEL",
           "PHONE_PAGES", "phone_may_call"]
