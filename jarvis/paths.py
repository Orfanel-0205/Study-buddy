"""Where Jarvis keeps its own data (settings, tasks, chat history, backups).

Jarvis never stores its data inside your project folders. The location is:

* Windows: %APPDATA%\\Jarvis
* macOS:   ~/Library/Application Support/Jarvis
* Linux:   $XDG_DATA_HOME/jarvis (usually ~/.local/share/jarvis)

Set the JARVIS_DATA_DIR environment variable (or pass --data-dir) to use another folder.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Jarvis"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Jarvis"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "jarvis"


def resolve_data_dir(override: str | os.PathLike | None = None) -> Path:
    raw = override or os.environ.get("JARVIS_DATA_DIR")
    path = Path(raw).expanduser() if raw else default_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    (path / "backups").mkdir(exist_ok=True)
    (path / "logs").mkdir(exist_ok=True)
    return path.resolve()
