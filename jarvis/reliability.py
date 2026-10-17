"""Keeping Jarvis dependable: daily backups and starting automatically with Windows."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

from .db import Database

KEEP_BACKUPS = 7


def daily_backup(db: Database, folder: Path, keep: int = KEEP_BACKUPS, today: date | None = None) -> Path | None:
    """Copy jarvis.db to <folder>/jarvis-YYYY-MM-DD.db once per day and keep the newest `keep` copies.

    Uses SQLite's online backup, so it's safe while Jarvis is running. Returns the new file, if any.
    """
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"jarvis-{(today or date.today()).isoformat()}.db"
    created = None
    if not target.exists():
        tmp = target.with_suffix(".tmp")
        src = sqlite3.connect(db.path)
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        tmp.replace(target)
        created = target
    for old in sorted(folder.glob("jarvis-*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    return created


# ------------------------------------------------------------------ start with Windows
def _startup_folder() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def autostart_path() -> Path:
    return _startup_folder() / "Jarvis.lnk"


def autostart_supported() -> bool:
    return sys.platform == "win32"


def autostart_enabled() -> bool:
    return autostart_supported() and autostart_path().exists()


def set_autostart(enabled: bool, project_root: Path, data_dir: Path | None = None) -> bool:
    """Add or remove a shortcut in your Windows Startup folder that starts Jarvis quietly
    (no window) when you sign in. Nothing else on the system is changed."""
    if not autostart_supported():
        raise OSError("Starting automatically is only supported on Windows.")
    link = autostart_path()
    if not enabled:
        link.unlink(missing_ok=True)
        return False
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")  # same Python, without a console window
    target = quiet if quiet.exists() else exe
    args = "-m jarvis --no-browser" + (f' --data-dir "{data_dir}"' if data_dir else "")
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:JARVIS_LINK); "
        "$s.TargetPath = $env:JARVIS_TARGET; $s.Arguments = $env:JARVIS_ARGS; "
        "$s.WorkingDirectory = $env:JARVIS_ROOT; $s.WindowStyle = 7; "
        "$s.Description = 'Start Jarvis (your local assistant)'; $s.Save()"
    )
    env = {**os.environ, "JARVIS_LINK": str(link), "JARVIS_TARGET": str(target), "JARVIS_ARGS": args,
           "JARVIS_ROOT": str(project_root)}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env, check=True,
                   capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return link.exists()
