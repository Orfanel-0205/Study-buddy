"""Download the tools needed to build the Jarvis Android app (one time, needs internet).

Downloads, verifies (checksums) and unpacks into %LOCALAPPDATA%\\JarvisAndroidTools
(or $JARVIS_ANDROID_TOOLS):
  * Eclipse Temurin JDK 17 (Java compiler/runtime)       ~190 MB
  * Android SDK build-tools 35.0.0 (aapt2, d8, apksigner)  ~60 MB
  * Android SDK platform 35 (android.jar)                  ~65 MB

The Android SDK parts are covered by the Android Software Development Kit License
Agreement (https://developer.android.com/studio/terms); by running this script you accept it,
just as you would when installing them with Android Studio.

No Android Studio or Gradle needed. Usage:  python android/setup_toolchain.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO = "https://dl.google.com/android/repository/"
BUILD_TOOLS = "build-tools;35.0.0"
PLATFORM = "platforms;android-35"
JDK_API = ("https://api.adoptium.net/v3/assets/latest/17/hotspot"
           "?architecture=x64&image_type=jdk&os={os}&vendor=eclipse")


def _open(url: str):
    # Some download servers reject Python's default User-Agent.
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "jarvis-setup/1.0"}), timeout=60)


def tools_dir() -> Path:
    base = os.environ.get("JARVIS_ANDROID_TOOLS") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share"), "JarvisAndroidTools")
    return Path(base)


def _download(url: str, dest: Path, algo: str, expected: str) -> None:
    print(f"  downloading {url}")
    h = hashlib.new(algo)
    with _open(url) as resp, dest.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d}% of {total // (1 << 20)} MB", end="", flush=True)
    print()
    if h.hexdigest().lower() != expected.lower():
        dest.unlink(missing_ok=True)
        raise SystemExit(f"Checksum mismatch for {url}; the download was discarded.")


def _extract(archive: Path, target: Path) -> None:
    """Unpack into a fresh, empty folder; refuse paths that would escape it."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            dest = (target / name).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise SystemExit(f"Unsafe path in {archive.name}: {name}")
        z.extractall(target)


def _single_child(folder: Path) -> Path:
    children = [p for p in folder.iterdir() if p.is_dir()]
    return children[0] if len(children) == 1 else folder


def _sdk_archive(root: ET.Element, path: str, host: str) -> tuple[str, str]:
    for pkg in root.iter("remotePackage"):
        if pkg.get("path") != path:
            continue
        for arch in pkg.iter("archive"):
            os_el = arch.find("host-os")
            if os_el is None or os_el.text == host:
                complete = arch.find("complete")
                return REPO + complete.findtext("url"), complete.findtext("checksum")
    raise SystemExit(f"{path} not found in Google's repository listing.")


def main() -> None:
    base = tools_dir()
    base.mkdir(parents=True, exist_ok=True)
    host = {"win32": "windows", "darwin": "macosx"}.get(sys.platform, "linux")
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        print("Reading Google's Android repository listing...")
        with _open(REPO + "repository2-3.xml") as resp:
            root = ET.fromstring(resp.read())
        for label, path, folder in [("build-tools", BUILD_TOOLS, "build-tools"), ("platform", PLATFORM, "platform")]:
            if (base / folder / "ok").exists():
                print(f"{label}: already installed")
                continue
            url, sha1 = _sdk_archive(root, path, host)
            archive = tmp / f"{folder}.zip"
            _download(url, archive, "sha1", sha1)
            _extract(archive, base / f"{folder}-unpacked")
            if (base / folder).exists():
                shutil.rmtree(base / folder)
            _single_child(base / f"{folder}-unpacked").rename(base / folder)
            shutil.rmtree(base / f"{folder}-unpacked", ignore_errors=True)
            (base / folder / "ok").write_text(path)
            print(f"{label}: installed")
        if (base / "jdk" / "ok").exists():
            print("JDK: already installed")
        else:
            jdk_os = {"windows": "windows", "macosx": "mac"}.get(host, "linux")
            with _open(JDK_API.format(os=jdk_os)) as resp:
                pkg = json.loads(resp.read())[0]["binary"]["package"]
            if not pkg["name"].endswith(".zip"):
                raise SystemExit("Only the .zip JDK package is supported by this script (Windows).")
            archive = tmp / "jdk.zip"
            _download(pkg["link"], archive, "sha256", pkg["checksum"])
            _extract(archive, base / "jdk-unpacked")
            if (base / "jdk").exists():
                shutil.rmtree(base / "jdk")
            _single_child(base / "jdk-unpacked").rename(base / "jdk")
            shutil.rmtree(base / "jdk-unpacked", ignore_errors=True)
            (base / "jdk" / "ok").write_text(pkg["name"])
            print("JDK: installed")
    print(f"\nAll tools ready in {base}")


if __name__ == "__main__":
    main()
