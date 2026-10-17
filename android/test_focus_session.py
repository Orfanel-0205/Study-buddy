"""Run the phone's focus-session tests (android/test/FocusSessionTest.java) on this computer.

    python android/test_focus_session.py

Uses the JDK that android/setup_toolchain.py installed (or `javac`/`java` on PATH).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def jdk_tool(name: str) -> str:
    exe = ".exe" if sys.platform == "win32" else ""
    bundled = Path(os.environ.get("LOCALAPPDATA", "")) / "JarvisAndroidTools" / "jdk" / "bin" / f"{name}{exe}"
    if bundled.exists():
        return str(bundled)
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found: run python android/setup_toolchain.py first.")
    return found


def main() -> int:
    sources = [HERE / "app" / "src" / "local" / "jarvis" / "assistant" / "FocusSession.java", HERE / "test" / "FocusSessionTest.java"]
    with tempfile.TemporaryDirectory() as out:
        subprocess.run([jdk_tool("javac"), "-encoding", "UTF-8", "-d", out, *map(str, sources)], check=True)
        return subprocess.run([jdk_tool("java"), "-cp", out, "local.jarvis.assistant.FocusSessionTest"]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
