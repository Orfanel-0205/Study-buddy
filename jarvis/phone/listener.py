"""The phone listener: a second, HTTPS-only server inside the same Jarvis process.

The computer keeps using http://127.0.0.1 (never reachable from the network).
When phone access is on, this listener also accepts connections from your
home network. Every request it receives is marked as coming from the phone,
so the security guard applies the stricter phone rules to it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket

import uvicorn

from .certs import CertInfo, ensure_certificates, lan_addresses

log = logging.getLogger(__name__)
PHONE_CHANNEL = "jarvis.channel"


class PhoneChannel:
    """ASGI wrapper that tags requests from the phone listener."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope = {**scope, PHONE_CHANNEL: "phone"}
        await self.app(scope, receive, send)


class _EmbeddedServer(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self):
        # The main (computer) server owns Ctrl+C handling; this one is stopped by Jarvis.
        yield


class PhoneListener:
    def __init__(self, app, data_dir, host: str | None = None):
        self.app = app
        self.cert_dir = data_dir / "phone"
        self.host = host or os.environ.get("JARVIS_PHONE_HOST", "0.0.0.0")
        self.hostname = socket.gethostname()
        self.port: int | None = None
        self.error = ""
        self.cert: CertInfo | None = None
        self.addresses: list[str] = []
        self._server: _EmbeddedServer | None = None
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return bool(self._server and self._server.started and self._task and not self._task.done())

    def info(self) -> dict:
        urls = [f"https://{ip}:{self.port}/m/" for ip in self.addresses] if self.running else []
        return {"running": self.running, "port": self.port, "error": self.error, "urls": urls,
                "computer": self.hostname,
                "fingerprint": self.cert.fingerprint if self.cert else "",
                "ca_fingerprint": self.cert.ca_fingerprint if self.cert else ""}

    async def start(self, port: int) -> dict:
        await self.stop()
        self.error = ""
        self.addresses = lan_addresses()
        if self.host not in ("0.0.0.0", "::"):
            self.addresses = [self.host]
        try:
            self.cert = await asyncio.to_thread(ensure_certificates, self.cert_dir, self.hostname, self.addresses)
        except Exception as exc:
            self.error = f"Could not prepare the HTTPS certificate: {exc}"
            return self.info()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # no port sharing tricks
            sock.bind((self.host, port))
            sock.listen(64)
        except OSError as exc:
            sock.close()
            self.error = f"Could not use port {port}: {exc.strerror or exc}. Pick another phone port in Settings."
            return self.info()
        self.port = sock.getsockname()[1]
        config = uvicorn.Config(PhoneChannel(self.app), lifespan="off", log_level="warning",
                                ssl_certfile=str(self.cert.certfile), ssl_keyfile=str(self.cert.keyfile),
                                timeout_graceful_shutdown=3, proxy_headers=False)
        server = _EmbeddedServer(config)
        self._server = server
        self._task = asyncio.create_task(self._run(server, sock), name="jarvis-phone-listener")
        for _ in range(100):  # wait up to ~5 s for it to come up
            if server.started or self._task.done():
                break
            await asyncio.sleep(0.05)
        if not self.running and not self.error:
            self.error = "The phone listener did not start. See the log file for details."
        return self.info()

    async def _run(self, server: uvicorn.Server, sock: socket.socket) -> None:
        try:
            await server.serve(sockets=[sock])
        except (SystemExit, Exception) as exc:  # uvicorn calls sys.exit on startup errors
            self.error = f"The phone listener stopped: {exc!r}"
            log.exception("Phone listener failed")
        finally:
            with contextlib.suppress(OSError):
                sock.close()

    async def stop(self) -> None:
        if self._server and self._task:
            self._server.should_exit = True
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._task, timeout=10)
        self._server = None
        self._task = None
