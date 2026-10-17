"""Start Jarvis:  python -m jarvis  [--port 8765] [--no-browser] [--data-dir PATH]"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

from . import __version__
from .paths import resolve_data_dir


def _free_port(preferred: int, avoid: int | None = None) -> int:
    for port in range(preferred, preferred + 20):
        if port == avoid:  # reserved for phone access
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port found between {preferred} and {preferred + 19}. Use --port to pick another.")


def _jarvis_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/", timeout=2) as resp:
            return b'name="jarvis-token"' in resp.read(4096)
    except Exception:
        return False


def _setup_command(args) -> None:
    import json
    import shutil
    import ssl

    from .activity import ActivityLog
    from .config import ConfigStore
    from .db import Database

    data_dir = resolve_data_dir(args.data_dir)
    if args.issue_device_token:
        from .phone.devices import DeviceRegistry
        db = Database(data_dir / "jarvis.db")
        device, token = DeviceRegistry(db, ActivityLog(db)).issue(args.issue_device_token)
        print(json.dumps({"token": token, "device": device}))
        return
    if not (args.sync_code and args.sync_ca):
        raise SystemExit("--sync-with needs --sync-code (from the laptop's Settings -> Phone access) and --sync-ca.")
    url = args.sync_with.rstrip("/")
    ctx = ssl.create_default_context(cafile=args.sync_ca)
    body = json.dumps({"code": args.sync_code, "name": "Jarvis on this phone"}).encode()
    req = urllib.request.Request(url + "/api/phone/pair", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            token = json.loads(resp.read())["token"]
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"The laptop refused: {exc.read().decode(errors='replace')}")
    (data_dir / "phone").mkdir(exist_ok=True)
    shutil.copyfile(args.sync_ca, data_dir / "phone" / "laptop-ca.pem")
    ConfigStore(data_dir).update({"sync_url": url, "sync_token": token})
    print(f"Paired with the laptop at {url}. Tasks and flashcards will sync automatically.")


def _run_pocket(args) -> None:
    """Jarvis on the phone: the mobile app on 127.0.0.1 only, with the phone rules (paired keys)."""
    url = f"http://127.0.0.1:{args.port}"
    try:
        with urllib.request.urlopen(url + "/m/manifest.webmanifest", timeout=2) as resp:
            if resp.status == 200:
                print(f"Jarvis is already running on this phone at {url}/m/")
                return
    except Exception:
        pass
    import uvicorn

    from .phone import PhoneChannel
    from .server import create_app

    data_dir = resolve_data_dir(args.data_dir)
    handler = logging.handlers.RotatingFileHandler(data_dir / "logs" / "jarvis.log", maxBytes=2_000_000,
                                                   backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(data_dir, pocket=True, restore_last_project=False)
    print(f"Jarvis {__version__} is running on this phone at {url}/m/ (only apps on this phone can reach it)")
    uvicorn.run(PhoneChannel(app), host="127.0.0.1", port=args.port, log_level="warning")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis: local AI assistant for tasks and software development")
    parser.add_argument("--port", type=int, help="port to listen on (default 8765; 8766 with --pocket)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    parser.add_argument("--data-dir", help="folder for settings, tasks and history (default: see README)")
    parser.add_argument("--version", action="version", version=f"Jarvis {__version__}")
    pocket = parser.add_argument_group("Jarvis on a phone (run inside Termux)")
    pocket.add_argument("--pocket", action="store_true",
                        help="run as Jarvis on this phone: only apps on this phone can reach it")
    pocket.add_argument("--issue-device-token", metavar="NAME",
                        help="print a key for the Jarvis app on this phone, then exit")
    pocket.add_argument("--sync-with", metavar="URL", help="pair with the laptop for syncing, e.g. https://192.168.1.23:8766")
    pocket.add_argument("--sync-code", metavar="CODE", help="6-digit pairing code shown on the laptop (with --sync-with)")
    pocket.add_argument("--sync-ca", metavar="FILE", help="the laptop's jarvis-ca.crt (with --sync-with)")
    args = parser.parse_args(argv)
    if args.port is None:
        args.port = 8766 if args.pocket else 8765
    if args.issue_device_token or args.sync_with:
        return _setup_command(args)
    if args.pocket:
        return _run_pocket(args)

    # Started without a console window (e.g. automatically at sign-in): give output somewhere to go.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    url = f"http://127.0.0.1:{args.port}"
    if _jarvis_running(url):
        # Already running (for example started automatically): just open it instead of a second copy.
        print(f"\n  Jarvis is already running at {url}\n")
        if not args.no_browser:
            webbrowser.open(url)
        return

    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import uvicorn
    except ImportError as exc:
        raise SystemExit(f"Missing dependency: {exc.name}. Run:  python -m pip install -r requirements.txt")

    data_dir = resolve_data_dir(args.data_dir)
    handler = logging.handlers.RotatingFileHandler(data_dir / "logs" / "jarvis.log", maxBytes=2_000_000,
                                                   backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from .config import ConfigStore
    from .server import create_app

    port = _free_port(args.port, avoid=ConfigStore(data_dir).get().phone_port)
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    app = create_app(data_dir, allowed_hosts=allowed, port=port)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Jarvis {__version__} is running at {url}")
    print("  It only accepts connections from this computer. Nothing is sent to the internet.")
    print(f"  Your data folder: {data_dir}")
    print("  Press Ctrl+C here to stop Jarvis.\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    print("Jarvis stopped.")


if __name__ == "__main__":
    sys.exit(main())
