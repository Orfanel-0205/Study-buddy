"""Images you attach to a chat or use to make flashcards (photos of notes, screenshots...).

They are kept only on this computer, in <data folder>/images, named by a hash of their
content (the same photo is stored once). Only real image files are accepted.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
_NAME = re.compile(r"^[0-9a-f]{64}\.(jpg|png|gif|webp)$")
MIME = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}


class ImageError(ValueError):
    pass


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def decode(value: str) -> bytes:
    """Accept a data: URL or plain base64."""
    if value.startswith("data:"):
        value = value.split(",", 1)[-1]
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("The image could not be read (it isn't valid base64).") from exc
    if len(data) > MAX_BYTES:
        raise ImageError(f"The image is too large ({len(data) // (1024 * 1024)} MB); the limit is 8 MB.")
    if not sniff(data):
        raise ImageError("That file isn't a supported image. Use a JPEG, PNG, GIF or WebP picture.")
    return data


class ImageStore:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    def save(self, value: str) -> str:
        data = decode(value)
        name = f"{hashlib.sha256(data).hexdigest()}.{sniff(data)}"
        path = self.folder / name
        if not path.exists():
            path.write_bytes(data)
        return name

    def path(self, name: str) -> Path:
        if not _NAME.match(name):
            raise ImageError("Unknown image.")
        path = self.folder / name
        if not path.exists():
            raise FileNotFoundError("That image no longer exists.")
        return path

    def base64(self, name: str) -> str:
        return base64.b64encode(self.path(name).read_bytes()).decode("ascii")
