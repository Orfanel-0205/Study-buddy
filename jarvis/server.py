"""The local web server that powers the Jarvis interface.

Security model (it can read your project and run commands, so this matters):
* The computer's interface listens on 127.0.0.1 only, so other computers cannot reach it.
* Every /api request from the computer must carry a random token generated at
  launch. The token is embedded in the page Jarvis serves; other websites open
  in your browser cannot read it, so they cannot drive Jarvis.
* The Host and Origin headers are checked to block DNS-rebinding tricks.
* Phone access (off by default) uses a separate HTTPS listener. Phones must be
  paired with a one-time code, and may only call an explicit allow-list of
  endpoints: no file changes, commands, settings or project selection.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import secrets
import socket
import csv
import io
import subprocess
import time
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .activity import ActivityLog
from .assistant.prompts import MODES
from .assistant.service import Assistant, ProviderHolder
from .config import ConfigStore, EndpointNotLocalError
from .conversations import ConversationNotFound, ConversationStore
from .db import Database, now_iso
from .llm import ProviderError, create_provider
from .phone import PHONE_CHANNEL, PHONE_PAGES, DeviceRegistry, PairingError, PhoneListener, phone_may_call
from .project import ProjectManager
from .project.changes import ChangeError, ChangeManager
from .project.commands import CommandError, CommandRunner, classify, split_command
from .images import MIME, ImageError, ImageStore
from .phone.certs import lan_addresses
from .project.workspace import AccessDenied
from .reliability import autostart_enabled, autostart_supported, daily_backup, set_autostart
from . import sync as sync_engine
from .study import CardIn, DeckIn, Grade, StudyNotFound, StudyStore
from .tasks import TaskIn, TaskNotFound, TaskStore, TaskUpdate
from .learn import exercises as exercise_bank
from .learn.api_lab import PracticeApi, make_router as make_api_lab
from .learn.decks import StarterDecks
from .learn.guides import GuideLibrary
from .learn.practice import PracticeStore, Runtimes, exercise_detail, exercise_list, run_code
from .learn.standup import standup as standup_note
from .motivation import ENTRIES as MOTIVATION_ENTRIES, pick as pick_motivation
from .build import catalog as build_catalog, hackathon as build_hackathon
from .checkins import CheckinIn, CheckinStore, advice as checkin_advice, insights as checkin_insights
from .focus import FocusMonitor
from .progress import progress as progress_report

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

FOLDER_PICKER = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
initial = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
path = filedialog.askdirectory(title='Choose a project folder for Jarvis', initialdir=initial, mustexist=True)
sys.stdout.write(path or '')
"""


# ---------------------------------------------------------------- request bodies
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: int | None = None
    mode: str = "general"
    detail: str | None = None
    use_project: bool = True
    attached: list[str] = Field(default_factory=list, max_length=20)
    stream_id: str = Field(default_factory=lambda: secrets.token_hex(8), max_length=64)
    run_tests: bool = False  # run the project's one-click test command first and show the result
    use_guides: bool = False  # include matching sections of Jarvis's built-in study guides
    lang: str = Field("en", pattern="^(en|ja)$")  # reply language
    wellbeing: str = Field("", max_length=400)  # today's check-in summary, if the user shared one
    images: list[Annotated[str, Field(max_length=12_000_000)]] = Field(default_factory=list, max_length=4)


class FocusSettings(BaseModel):
    focus_enabled: bool | None = None
    focus_grace_minutes: int | None = Field(None, ge=1, le=120)
    focus_cooldown_minutes: int | None = Field(None, ge=1, le=240)
    focus_apps: list[Annotated[str, Field(max_length=80)]] | None = Field(None, max_length=60)


class SnoozeRequest(BaseModel):
    minutes: int = Field(15, ge=1, le=240)
    break_: bool = Field(False, alias="break")


def pick_motivation_entries() -> list[dict]:
    """The verses and quotes, for the phone's offline copy."""
    return [{k: e[k] for k in ("id", "kind", "source", "themes", "text", "school") if k in e} for e in MOTIVATION_ENTRIES]


class PocketModel(BaseModel):
    model: str = Field(min_length=1, max_length=120)


class PageCompanion(BaseModel):
    pose: str = Field(pattern=r"^(cheer|code|study|idea|sleepy|celebrate|pouty|care|relax)$")
    message: str = Field("", max_length=300)


class OverlayRequest(BaseModel):
    enabled: bool | None = None
    pack: str | None = Field(None, pattern=r"^study-buddy-\d$")


class PlanRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=4000)
    language: str = Field("any", pattern="^(any|php|python|js|ts)$")


class HackathonRequest(BaseModel):
    name: str = Field("Hackathon", max_length=120)
    start: str = Field(max_length=40)
    hours: float = Field(24, ge=2, le=96)
    team: list[Annotated[str, Field(max_length=60)]] = Field(default_factory=list, max_length=8)
    theme: str = Field("", max_length=300)
    criteria: list[str] = Field(default_factory=list, max_length=10)
    add_tasks: bool = False


class PracticeCode(BaseModel):
    code: str = Field(max_length=50_000)


class HintRequest(BaseModel):
    code: str = Field("", max_length=50_000)
    results: list[dict] = Field(default_factory=list, max_length=50)
    question: str = Field("", max_length=2000)


class CancelRequest(BaseModel):
    stream_id: str


class OpenProjectRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    approved: bool = False
    acknowledge_risk: bool = False


class ProposeRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str | None = None
    delete: bool = False
    note: str = ""
    source: str = "assistant"


class ApplyRequest(BaseModel):
    confirmed: bool = False


class UndoRequest(BaseModel):
    force: bool = False


class SubtasksRequest(BaseModel):
    steps: list[dict] = Field(min_length=1, max_length=30)


class StudyCardsRequest(BaseModel):
    cards: list[CardIn] = Field(min_length=1, max_length=500)


class ReviewRequest(BaseModel):
    grade: Grade
    reviewed_on: date | None = None  # reviews made offline on the phone keep their real day


class GenerateCardsRequest(BaseModel):
    text: str = Field("", max_length=20000)
    images: list[Annotated[str, Field(max_length=12_000_000)]] = Field(default_factory=list, max_length=4)
    count: int = Field(10, ge=1, le=40)


class ImportCardsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)


class SyncRequest(BaseModel):
    since: str = Field("", max_length=40)
    changes: dict


class AutostartRequest(BaseModel):
    enabled: bool


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class PairRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12)
    name: str = Field("Phone", max_length=60)


# ---------------------------------------------------------------- security middleware
class JarvisGuard:
    """Checks every request before it reaches a route.

    Computer (127.0.0.1 listener): session token + Host/Origin checks.
    Phone (HTTPS listener, tagged by PhoneChannel): pairing token + allow-list.
    """

    def __init__(self, app, token: str, allowed_hosts: set[str], devices: DeviceRegistry, pocket: bool = False):
        self.app = app
        self.token = token
        self.allowed_hosts = allowed_hosts
        self.devices = devices
        self.pocket = pocket
        name = socket.gethostname().lower()
        self.machine_names = {name, f"{name}.local", "localhost"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if scope.get(PHONE_CHANNEL) == "phone":
            return await self._phone(scope, receive, send, headers)
        host = headers.get("host", "")
        if self.allowed_hosts and host not in self.allowed_hosts:
            return await _plain(send, 403, "Jarvis only accepts requests addressed to this computer.")
        origin = headers.get("origin")
        if origin and self.allowed_hosts and origin.split("://", 1)[-1] not in self.allowed_hosts:
            return await _plain(send, 403, "Requests from other websites are not allowed.")
        if scope["path"].startswith("/api/") and not secrets.compare_digest(
                headers.get("x-jarvis-token", ""), self.token):
            return await _plain(send, 403, "Missing or outdated session token. Reload the Jarvis page.")
        return await self.app(scope, receive, send)

    def _phone_host_ok(self, host: str) -> bool:
        # Only addresses and this computer's own name: blocks DNS-rebinding via other domains.
        hostname = (urlsplit("//" + host).hostname or "").lower()
        if hostname in self.machine_names:
            return True
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False

    async def _phone(self, scope, receive, send, headers):
        host = headers.get("host", "")
        if not self._phone_host_ok(host):
            return await _plain(send, 403, "Open Jarvis using your computer's network address (shown in its Settings).")
        origin = headers.get("origin")
        if origin and origin.split("://", 1)[-1] != host:
            return await _plain(send, 403, "Requests from other websites are not allowed.")
        path, method = scope["path"], scope["method"]
        if path == "/":
            return await _redirect(send, "/m/")
        if method in ("GET", "HEAD") and PHONE_PAGES.match(path):
            return await self.app(scope, receive, send)
        if method == "POST" and path == "/api/phone/pair":
            return await self.app(scope, receive, send)
        if path.startswith("/practice/"):
            # The API Lab has its own practice logins. On the phone's own Jarvis only apps on the phone can
            # reach it; the laptop never offers it to the network.
            if self.pocket:
                return await self.app(scope, receive, send)
            return await _plain(send, 403, "The API Lab only runs on the device itself. Use it on your computer, "
                                           "or with Jarvis on this phone.")
        if phone_may_call(method, path, self.pocket):
            auth = headers.get("authorization", "")
            device = self.devices.verify(auth[7:].strip() if auth.lower().startswith("bearer ") else "")
            if not device:
                return await _plain(send, 401, "This phone isn't paired with Jarvis (or was removed). Pair it again.",
                                    code="unpaired")
            return await self.app({**scope, "jarvis.device": device}, receive, send)
        return await _plain(send, 403, "That isn't available from the phone. Use Jarvis on your computer for it.")


async def _plain(send, status: int, message: str, **extra):
    body = json.dumps({"detail": message, **extra}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


async def _redirect(send, location: str):
    await send({"type": "http.response.start", "status": 307,
                "headers": [(b"location", location.encode()), (b"content-length", b"0")]})
    await send({"type": "http.response.body", "body": b""})


class RevalidatingStatic(StaticFiles):
    """Static files that browsers re-check (cheaply, via ETag) on every load, so phones and
    browsers never keep running an outdated copy of the app after Jarvis is updated."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def via(request: Request) -> str:
    """Suffix for activity entries that came from a phone."""
    device = request.scope.get("jarvis.device")
    return f" (from phone '{device['name']}')" if device else ""


class OverlayProcess:
    """Study Buddy's floating window (jarvis/overlay.py) as a separate process, so it can never slow Jarvis down."""

    def __init__(self, port: int, token: str, data_dir: Path):
        self.port, self.token, self.data_dir = port, token, data_dir
        self.proc: subprocess.Popen | None = None
        self.supported = sys.platform == "win32"

    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def start(self) -> None:
        if not self.supported or self.running():
            return
        exe = Path(sys.executable)
        quiet = exe.with_name("pythonw.exe")
        try:
            self.proc = subprocess.Popen(
                [str(quiet if quiet.exists() else exe), "-m", "jarvis.overlay", "--port", str(self.port), "--data-dir", str(self.data_dir)],
                cwd=str(Path(__file__).resolve().parent.parent), env={**os.environ, "JARVIS_OVERLAY_TOKEN": self.token},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            log.warning("Could not start Study Buddy's floating window: %s", exc)

    def stop(self) -> None:
        if self.running():
            self.proc.terminate()
        self.proc = None


# ---------------------------------------------------------------- app factory
def create_app(data_dir: Path, *, token: str | None = None, allowed_hosts: set[str] | None = None,
               provider_factory=create_provider, restore_last_project: bool = True,
               phone_host: str | None = None, pocket: bool = False, port: int = 8765) -> FastAPI:
    """pocket=True: Jarvis running on the phone itself (only reachable by apps on the phone,
    through the phone rules), syncing tasks and flashcards with the laptop."""
    token = token or secrets.token_urlsafe(32)
    config = ConfigStore(data_dir)
    db = Database(data_dir / "jarvis.db")
    activity = ActivityLog(db)
    tasks = TaskStore(db)
    conversations = ConversationStore(db)
    projects = ProjectManager(config, activity, db)
    changes = ChangeManager(db, data_dir, activity)
    holder = ProviderHolder(config, provider_factory)

    def _command_done(run):
        activity.record("command_finished", f"'{run.command}' {run.status} (exit code {run.exit_code})",
                        command=run.command, status=run.status, exit_code=run.exit_code,
                        seconds=round((run.ended or 0) - run.started, 1))

    runner = CommandRunner(on_finish=_command_done)
    image_store = ImageStore(data_dir / "images")
    study = StudyStore(db)
    guides = GuideLibrary()
    starter_decks = StarterDecks(db)
    practice = PracticeStore(db)
    runtimes = Runtimes()
    api_lab = PracticeApi()
    checkins = CheckinStore(db)
    focus = FocusMonitor(config, db)
    overlay = OverlayProcess(port, token, data_dir)
    break_until = {"t": 0.0}
    page_pose = {"pose": "", "at": 0.0, "message": "", "seq": 0}  # what Study Buddy shows in the open Jarvis page
    assistant = Assistant(config, holder, conversations, projects, activity, runner, image_store, guides)
    devices = DeviceRegistry(db, activity)
    overview_cache: dict[str, dict] = {}

    async def _upkeep() -> None:
        """Every few minutes: make the daily backup, and follow network address changes so phones
        keep a valid certificate (for example after the router gives this computer a new address)."""
        while True:
            try:
                if config.get().daily_backup:
                    made = await asyncio.to_thread(daily_backup, db, data_dir / "backups" / "daily")
                    if made:
                        activity.record("backup", f"Daily backup saved: {made.name}", path=str(made))
                await _sync_once()
                if phone.running and phone.host in ("0.0.0.0", "::"):
                    current = await asyncio.to_thread(lan_addresses)
                    if current and set(current) != set(phone.addresses):
                        info = await phone.start(config.get().phone_port)
                        activity.record("phone_access", "Network address changed; phone access restarted with "
                                        f"a matching certificate ({', '.join(current)})", **info)
            except Exception:
                log.exception("Upkeep failed")
            await asyncio.sleep(config.get().sync_interval if pocket else 300)

    sync_ca = data_dir / "phone" / "laptop-ca.pem"

    async def _sync_once() -> dict | None:
        s = config.get()
        if not (pocket and s.sync_url and s.sync_token):
            return None
        try:
            result = await sync_engine.sync_with(db, s.sync_url, s.sync_token, sync_ca if sync_ca.exists() else None)
        except Exception as exc:
            log.info("Sync with the laptop failed: %s", exc)
            return None
        got = result["received"]
        if any(got.values()):
            activity.record("sync", f"Synced with the laptop: {got['tasks']} task(s), {got['decks']} deck(s), "
                            f"{got['cards']} card(s) updated, {got['deleted']} deleted", **result)
        return result

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        activity.record("session_started", f"Jarvis {__version__} started")
        last = config.get().last_project
        if restore_last_project and last:
            try:
                await asyncio.to_thread(projects.open, last)
            except Exception as exc:
                log.warning("Could not reopen last project %s: %s", last, exc)
        if config.get().phone_access and not pocket:  # a pocket Jarvis is only reachable on the phone itself
            info = await phone.start(config.get().phone_port)
            if info["error"]:
                log.warning("Phone access could not start: %s", info["error"])
        upkeep = asyncio.create_task(_upkeep(), name="jarvis-upkeep")
        if not pocket:
            focus.start()
            if config.get().overlay_enabled:
                overlay.start()
        yield
        upkeep.cancel()
        focus.stop()
        overlay.stop()
        await phone.stop()
        runner.cancel_all()
        projects.index.cancel()
        await holder.aclose()

    app = FastAPI(title="Jarvis", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(JarvisGuard, token=token, allowed_hosts=allowed_hosts or set(), devices=devices, pocket=pocket)
    phone = PhoneListener(app, data_dir, host=phone_host)
    app.state.token = token
    app.state.config = config
    app.state.projects = projects
    app.state.runner = runner
    app.state.devices = devices
    app.state.phone = phone
    app.state.api_lab = api_lab

    # ------------------------------------------------------------ errors -> friendly JSON
    def _err(status: int):
        async def handler(request: Request, exc: Exception):
            return JSONResponse({"detail": str(exc) or exc.__class__.__name__}, status_code=status)
        return handler

    for exc_type, status in [(AccessDenied, 403), (PermissionError, 403), (FileNotFoundError, 404),
                             (NotADirectoryError, 400), (TaskNotFound, 404), (ConversationNotFound, 404),
                             (ChangeError, 400), (CommandError, 400), (EndpointNotLocalError, 400)]:
        app.add_exception_handler(exc_type, _err(status))

    app.add_exception_handler(StudyNotFound, _err(404))
    app.add_exception_handler(ImageError, _err(400))

    @app.exception_handler(PairingError)
    async def _pairing_error(request: Request, exc: PairingError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(ProviderError)
    async def _provider_error(request: Request, exc: ProviderError):
        return JSONResponse({"detail": exc.message, "hint": exc.hint, "code": exc.code}, status_code=503)

    @app.exception_handler(ValidationError)
    async def _validation_error(request: Request, exc: ValidationError):
        msgs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse({"detail": "Invalid value — " + "; ".join(msgs)}, status_code=422)

    def require_ws():
        if not projects.workspace:
            raise HTTPException(400, "Open a project folder first (Project tab).")
        return projects.workspace

    # ------------------------------------------------------------ page
    @app.get("/", response_class=HTMLResponse)
    def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("{{JARVIS_TOKEN}}", token).replace("{{VERSION}}", __version__),
                            headers={"Cache-Control": "no-store"})

    app.mount("/static", RevalidatingStatic(directory=STATIC_DIR), name="static")

    # ------------------------------------------------------------ mobile app (served to the phone)
    def _templated(name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8").replace("{{VERSION}}", __version__)

    @app.get("/m", include_in_schema=False)
    def mobile_redirect():
        return RedirectResponse("/m/", status_code=307)

    @app.get("/m/", response_class=HTMLResponse)
    def mobile_page():
        return HTMLResponse(_templated("mobile.html"), headers={"Cache-Control": "no-cache"})

    @app.get("/m/sw.js")
    def mobile_service_worker():
        return Response(_templated("sw.js"), media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/m/manifest.webmanifest")
    def mobile_manifest():
        return Response(_templated("manifest.webmanifest"), media_type="application/manifest+json")

    @app.get("/m/jarvis-ca.crt")
    def mobile_ca_certificate():
        ca = data_dir / "phone" / "jarvis-ca.crt"
        if not ca.exists():
            raise HTTPException(404, "Turn on phone access first.")
        return Response(ca.read_bytes(), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": 'attachment; filename="jarvis-ca.crt"'})

    # ------------------------------------------------------------ status & settings
    @app.get("/api/status")
    async def status():
        model = await holder.status()
        ws = projects.workspace
        return {"app_version": __version__, "session_id": activity.session_id, "data_dir": str(data_dir),
                "model": model,
                "project": {"open": bool(ws), "name": ws.name if ws else "", "root": str(ws.root) if ws else "",
                            "can_run_tests": bool(ws and assistant._test_preset())},
                "phone": {"enabled": config.get().phone_access, "running": phone.running},
                "pocket": pocket,
                "modes": [{"id": k, "label": v["label"], "hint": v["hint"]} for k, v in MODES.items()]}

    @app.get("/api/settings")
    def get_settings():
        return {"settings": config.get().model_dump(), "paths": {
            "data_dir": str(data_dir), "config": str(config.path), "database": str(db.path),
            "backups": str(data_dir / "backups"), "logs": str(data_dir / "logs")}}

    @app.put("/api/settings")
    async def put_settings(changes: dict):
        before = config.get()
        changes.pop("last_project", None)
        changes.pop("recent_projects", None)
        after = config.update(changes)
        changed = sorted(k for k in changes if getattr(before, k, None) != getattr(after, k, None))
        if changed:
            activity.record("settings_changed", "Changed settings: " + ", ".join(changed), changed=changed)
        if projects.workspace and ({"extra_exclude_patterns", "max_file_bytes", "max_index_files"} & set(changed)):
            await asyncio.to_thread(projects.open, str(projects.workspace.root))  # re-apply rules and re-index
            overview_cache.clear()
        if {"phone_access", "phone_port"} & set(changed):
            if after.phone_access:
                info = await phone.start(after.phone_port)
                activity.record("phone_access", "Turned phone access on" if not info["error"] else
                                f"Phone access could not start: {info['error']}", **info)
            else:
                await phone.stop()
                devices.cancel_code()
                activity.record("phone_access", "Turned phone access off")
        return {"settings": after.model_dump()}

    # ------------------------------------------------------------ phone pairing
    @app.get("/api/phone")
    def phone_status():
        return {"enabled": config.get().phone_access, **phone.info(), "devices": devices.list(),
                "pairing": devices.code_info()}

    @app.post("/api/phone/pairing-code")
    def phone_pairing_code():
        if not phone.running:
            raise HTTPException(400, "Turn on phone access first.")
        return devices.new_code()

    @app.delete("/api/phone/pairing-code")
    def phone_cancel_code():
        devices.cancel_code()
        return {"ok": True}

    @app.delete("/api/phone/devices/{device_id}")
    def phone_remove_device(device_id: int):
        devices.revoke(device_id)
        return {"ok": True}

    @app.post("/api/phone/pair")
    def phone_pair(body: PairRequest, request: Request):
        if request.scope.get(PHONE_CHANNEL) != "phone":
            raise HTTPException(400, "Pairing is done from the phone app.")
        client = request.client.host if request.client else "unknown"
        device, device_token = devices.pair(body.code, body.name, client)
        return {"token": device_token, "device": device, "computer": phone.hostname}

    @app.get("/api/phone/whoami")
    def phone_whoami(request: Request):
        return {"device": request.scope["jarvis.device"], "computer": phone.hostname, "app_version": __version__}

    @app.post("/api/phone/unpair")
    def phone_unpair(request: Request):
        devices.revoke(request.scope["jarvis.device"]["id"], by_phone=True)
        return {"ok": True}

    # ------------------------------------------------------------ chat
    @app.get("/api/conversations")
    def list_conversations():
        return conversations.list()

    @app.get("/api/conversations/{conv_id}")
    def get_conversation(conv_id: int):
        return {"conversation": conversations.get(conv_id), "messages": conversations.messages(conv_id)}

    @app.patch("/api/conversations/{conv_id}")
    def rename_conversation(conv_id: int, body: RenameRequest):
        return conversations.rename(conv_id, body.title)

    @app.delete("/api/conversations/{conv_id}")
    def delete_conversation(conv_id: int):
        conversations.delete(conv_id)
        return {"ok": True}

    @app.post("/api/chat")
    async def chat(req: ChatRequest, request: Request):
        if req.conversation_id:
            conversations.get(req.conversation_id)  # 404 before streaming starts
        from_phone = bool(request.scope.get("jarvis.device"))
        image_names = [await asyncio.to_thread(image_store.save, value) for value in req.images]

        async def events():
            async for event in assistant.chat(
                    message=req.message, conversation_id=req.conversation_id, mode=req.mode,
                    detail=req.detail, use_project=req.use_project,
                    attached=[] if from_phone else req.attached,  # phones can't pick files to send
                    stream_id=req.stream_id, origin=via(request),
                    run_tests=req.run_tests and not from_phone,  # commands only start from the computer
                    images=image_names, use_guides=req.use_guides, lang=req.lang, wellbeing=req.wellbeing):
                yield json.dumps(event) + "\n"

        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/chat/cancel")
    def cancel_chat(body: CancelRequest):
        return {"cancelled": assistant.cancel(body.stream_id)}

    # ------------------------------------------------------------ tasks
    @app.get("/api/tasks")
    def list_tasks(status: str | None = None, project: str | None = None, include_done: bool = True):
        return tasks.list(status=status or None, project=project or None, include_done=include_done)

    @app.get("/api/tasks/projects")
    def task_projects():
        return tasks.projects()

    @app.get("/api/tasks/export")
    def export_tasks():
        body = json.dumps({"exported_by": f"Jarvis {__version__}", "tasks": tasks.list()}, indent=2)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="jarvis-tasks.json"'})

    @app.post("/api/tasks")
    def create_task(body: TaskIn, request: Request):
        task = tasks.create(body)
        activity.record("task_created", f"Created task '{task['title']}'{via(request)}", task_id=task["id"])
        return task

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id: int, body: TaskUpdate, request: Request):
        before = tasks.get(task_id)
        task = tasks.update(task_id, body)
        what = "Completed" if task["status"] == "done" and before["status"] != "done" else "Updated"
        activity.record("task_updated", f"{what} task '{task['title']}'{via(request)}", task_id=task_id,
                        fields=sorted(body.model_dump(exclude_unset=True)))
        return task

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: int, request: Request):
        task = tasks.delete(task_id)
        activity.record("task_deleted", f"Deleted task '{task['title']}' (and its subtasks){via(request)}",
                        task_id=task_id)
        return {"ok": True}

    @app.post("/api/tasks/{task_id}/breakdown")
    async def breakdown(task_id: int):
        return await assistant.breakdown_task(tasks.get(task_id))

    @app.post("/api/tasks/{task_id}/subtasks")
    def add_subtasks(task_id: int, body: SubtasksRequest, request: Request):
        parent = tasks.get(task_id)
        created = []
        for step in body.steps:
            created.append(tasks.create(TaskIn(
                title=str(step.get("title", "")).strip()[:300] or "Step",
                description=str(step.get("description", ""))[:20000], parent_id=task_id,
                project=parent["project"], project_path=parent["project_path"], priority=parent["priority"])))
        activity.record("task_created", f"Added {len(created)} steps to '{parent['title']}'{via(request)}",
                        task_id=task_id)
        return created

    @app.post("/api/tasks/plan")
    async def plan(project: str | None = None):
        return await assistant.plan_tasks(tasks.list(project=project or None, include_done=False))

    # ------------------------------------------------------------ project
    def project_info():
        ws = projects.workspace
        if not ws:
            return {"open": False, "recent": config.get().recent_projects}
        from dataclasses import asdict
        return {"open": True, "name": ws.name, "root": str(ws.root), "index": asdict(projects.index.status),
                "presets": [{k: v for k, v in p.items() if k != "argv"} for p in projects.presets],
                "recent": config.get().recent_projects, "overview": overview_cache.get(str(ws.root))}

    @app.get("/api/project")
    async def get_project():
        ws = projects.workspace
        if ws and str(ws.root) not in overview_cache:
            overview_cache[str(ws.root)] = await asyncio.to_thread(ws.overview)
        return project_info()

    @app.post("/api/project/open")
    def open_project(body: OpenProjectRequest):
        projects.open(body.path.strip().strip('"'))
        overview_cache.clear()
        return project_info()

    @app.post("/api/project/close")
    def close_project():
        projects.close()
        return project_info()

    @app.post("/api/project/pick")
    async def pick_folder():
        initial = str(projects.workspace.root.parent) if projects.workspace else ""
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            result = await asyncio.to_thread(
                subprocess.run, [sys.executable, "-c", FOLDER_PICKER, initial],
                capture_output=True, text=True, timeout=600, **kwargs)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(500, f"Could not open the folder picker ({exc}). Paste the folder path instead.")
        if result.returncode != 0:
            raise HTTPException(500, "The folder picker is not available on this system. Paste the folder path instead.")
        return {"path": result.stdout.strip()}

    @app.post("/api/project/reindex")
    def reindex():
        require_ws()
        projects.refresh_presets()
        overview_cache.clear()
        projects.reindex()
        return project_info()

    @app.post("/api/project/index/cancel")
    def cancel_index():
        projects.index.cancel()
        return {"ok": True}

    @app.get("/api/project/tree")
    def tree(path: str = ""):
        return require_ws().list_dir(path)

    @app.get("/api/project/file")
    def read_file(path: str):
        ws = require_ws()
        content = ws.read_text(path)
        return {"path": ws.rel(ws.resolve(path)), "content": content, "lines": len(content.splitlines()),
                "size": len(content.encode("utf-8"))}

    @app.get("/api/project/search")
    def search(q: str):
        require_ws()
        return [{**{k: v for k, v in h.items() if k != "text"}, "preview": h["text"][:400]}
                for h in projects.index.search(q, k=15, per_file=3)]

    # ------------------------------------------------------------ commands
    @app.post("/api/commands/check")
    def check_command(body: CommandRequest):
        require_ws()
        argv = split_command(body.command)
        return {"command": body.command, "argv": argv, **classify(argv, projects.presets)}

    @app.post("/api/commands/run")
    def run_command(body: CommandRequest):
        ws = require_ws()
        argv = split_command(body.command)
        risk = classify(argv, projects.presets)
        if risk["level"] != "safe" and not body.approved:
            raise HTTPException(400, "This command needs your approval before it runs.")
        if risk["level"] == "danger" and not body.acknowledge_risk:
            raise HTTPException(400, "This command is risky; confirm that you understand the risk first.")
        run = runner.start(body.command, argv, ws, risk["level"], config.get().command_timeout)
        activity.record("command_started", f"Ran '{body.command}' in {ws.name} ({risk['level']})",
                        command=body.command, level=risk["level"], run_id=run.id,
                        approved=body.approved, reasons=risk["reasons"])
        return run.to_dict()

    @app.get("/api/commands/{run_id}")
    def command_status(run_id: str, since: int = 0):
        try:
            return runner.get(run_id).to_dict(since)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @app.post("/api/commands/{run_id}/cancel")
    def cancel_command(run_id: str):
        try:
            return runner.cancel(run_id).to_dict()
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    # ------------------------------------------------------------ file changes
    @app.get("/api/changes")
    def list_changes(status: str | None = None):
        ws = projects.workspace
        return changes.list(project_root=str(ws.root) if ws else None, status=status or None)

    @app.post("/api/changes")
    def propose_change(body: ProposeRequest):
        ws = require_ws()
        if body.delete:
            content = None
        elif body.content is None:
            raise HTTPException(400, "Provide the new file content, or set delete=true.")
        else:
            content = body.content
        source = body.source if body.source in ("assistant", "manual") else "assistant"
        return changes.propose(ws, body.path, content, source=source, note=body.note)

    @app.get("/api/changes/{pid}")
    def get_change(pid: int):
        return changes.get(pid)

    @app.post("/api/changes/{pid}/apply")
    def apply_change(pid: int, body: ApplyRequest):
        result = changes.apply(projects.workspace, pid, confirmed=body.confirmed)
        projects.reindex()
        return result

    @app.post("/api/changes/{pid}/reject")
    def reject_change(pid: int):
        return changes.reject(pid)

    @app.post("/api/changes/{pid}/undo")
    def undo_change(pid: int, body: UndoRequest):
        result = changes.undo(projects.workspace, pid, force=body.force)
        projects.reindex()
        return result

    # ------------------------------------------------------------ sync (laptop side receives, phone side asks)
    @app.post("/api/sync")
    def sync_endpoint(body: SyncRequest, request: Request):
        device = request.scope.get("jarvis.device")
        if not device:
            raise HTTPException(403, "Only a paired Jarvis on a phone can sync.")
        server_time = now_iso()
        counts = sync_engine.apply(db, body.changes)
        outgoing = sync_engine.collect(db, body.since)
        if any(counts.values()):
            activity.record("sync", f"Synced with '{device['name']}': {counts['tasks']} task(s), {counts['decks']} "
                            f"deck(s), {counts['cards']} card(s) updated, {counts['deleted']} deleted", **counts)
        return {"server_time": server_time, "changes": outgoing}

    # ------------------------------------------------------------ Jarvis on the phone: choose its model there
    @app.get("/api/pocket/model")
    async def pocket_model():
        if not pocket:
            raise HTTPException(404, "Only Jarvis on the phone chooses its model here.")
        st = await holder.status()
        s = config.get()
        return {"model": st.get("model") or s.model, "models": st.get("models", []), "max_answer_tokens": s.max_answer_tokens}

    @app.put("/api/pocket/model")
    async def put_pocket_model(body: PocketModel, request: Request):
        """One model for chat, coding and (if it can read pictures) photos: two at once wouldn't fit a phone."""
        if not pocket:
            raise HTTPException(404, "Only Jarvis on the phone chooses its model here.")
        models = (await holder.status()).get("models", [])
        chosen = next((m for m in models if m["name"] == body.model), None)
        if not chosen:
            raise HTTPException(400, f"'{body.model}' isn't installed on this phone.")
        changes = {"model": body.model, "code_model": ""}
        if "vision" in (chosen.get("capabilities") or []):
            changes["vision_model"] = body.model
        config.update(changes)
        activity.record("settings_changed", f"Model on this phone: {body.model}{via(request)}")
        return {"model": body.model, "vision_model": config.get().vision_model}

    @app.get("/api/sync/status")
    def sync_status():
        s = config.get()
        if not (pocket and s.sync_url):
            return {"enabled": False, "pocket": pocket}
        st = sync_engine.state(db, s.sync_url.rstrip("/"))
        return {"enabled": True, "pocket": pocket, "peer": s.sync_url, "last_ok": st["last_ok"],
                "last_error": st["last_error"]}

    @app.post("/api/sync/now")
    async def sync_now():
        result = await _sync_once()
        if result is None:
            st = sync_engine.state(db, config.get().sync_url.rstrip("/"))
            raise HTTPException(503, st["last_error"] or "Sync isn't set up on this copy of Jarvis.")
        return result

    # ------------------------------------------------------------ images
    @app.get("/api/images/{name}")
    def get_image(name: str):
        path = image_store.path(name)
        return FileResponse(path, media_type=MIME[path.suffix[1:]],
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

    # ------------------------------------------------------------ study (flashcards)
    @app.get("/api/study/decks")
    def list_decks():
        return study.decks()

    @app.post("/api/study/decks")
    def create_deck(body: DeckIn, request: Request):
        deck = study.create_deck(body)
        activity.record("study", f"Created deck '{deck['name']}'{via(request)}", deck_id=deck["id"])
        return deck

    @app.patch("/api/study/decks/{deck_id}")
    def update_deck(deck_id: int, body: DeckIn):
        return study.update_deck(deck_id, body)

    @app.delete("/api/study/decks/{deck_id}")
    def delete_deck(deck_id: int, request: Request):
        deck = study.delete_deck(deck_id)
        activity.record("study", f"Deleted deck '{deck['name']}' and its cards{via(request)}", deck_id=deck_id)
        return {"ok": True}

    @app.get("/api/study/decks/{deck_id}/cards")
    def deck_cards(deck_id: int):
        return study.cards(deck_id)

    @app.post("/api/study/decks/{deck_id}/cards")
    def add_cards(deck_id: int, body: StudyCardsRequest, request: Request):
        cards = study.add_cards(deck_id, body.cards)
        activity.record("study", f"Added {len(cards)} card(s) to '{study.deck(deck_id)['name']}'{via(request)}",
                        deck_id=deck_id)
        return cards

    @app.patch("/api/study/cards/{card_id}")
    def update_card(card_id: int, body: CardIn):
        return study.update_card(card_id, body)

    @app.delete("/api/study/cards/{card_id}")
    def delete_card(card_id: int):
        study.delete_card(card_id)
        return {"ok": True}

    @app.get("/api/study/due")
    def due_cards(deck_id: int | None = None, within_days: int = 0):
        return study.due(deck_id, within_days=max(0, min(within_days, 30)), limit=500 if within_days else 200)

    @app.post("/api/study/cards/{card_id}/review")
    def review_card(card_id: int, body: ReviewRequest):
        return study.review(card_id, body.grade, body.reviewed_on)

    @app.post("/api/study/generate")
    async def generate_cards(body: GenerateCardsRequest):
        if not body.text.strip() and not body.images:
            raise HTTPException(400, "Paste some notes or add a photo to make flashcards from.")
        names = [await asyncio.to_thread(image_store.save, value) for value in body.images]
        return await assistant.make_flashcards(body.text, names, body.count)

    @app.get("/api/study/decks/{deck_id}/export")
    def export_deck(deck_id: int):
        deck = study.deck(deck_id)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["front", "back"])
        for card in study.cards(deck_id):
            writer.writerow([card["front"], card["back"]])
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in deck["name"]).strip() or "deck"
        return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'})

    @app.post("/api/study/decks/{deck_id}/import")
    def import_cards(deck_id: int, body: ImportCardsRequest):
        """Accepts CSV (front,back) or tab-separated text, as exported by Anki or Quizlet."""
        lines = [line for line in body.text.splitlines() if line.strip() and not line.startswith("#")]
        delimiter = "\t" if lines and "\t" in lines[0] else ","
        cards = []
        for row in csv.reader(lines, delimiter=delimiter):
            if len(row) >= 2 and row[0].strip() and row[1].strip():
                if (row[0].strip().lower(), row[1].strip().lower()) in (("front", "back"), ("term", "definition")):
                    continue  # header row
                cards.append(CardIn(front=row[0].strip()[:2000], back=row[1].strip()[:4000]))
        if not cards:
            raise HTTPException(400, "No cards found. Use one card per line: front and back separated by a comma or a tab.")
        return {"added": len(study.add_cards(deck_id, cards))}

    # ------------------------------------------------------------ system (start with Windows)
    @app.get("/api/system/autostart")
    def get_autostart():
        return {"supported": autostart_supported(), "enabled": autostart_enabled()}

    @app.put("/api/system/autostart")
    def put_autostart(body: AutostartRequest):
        default_dir = Path(os.environ.get("APPDATA", "")) / "Jarvis"
        custom = None if Path(data_dir).resolve() == default_dir.resolve() else data_dir
        enabled = set_autostart(body.enabled, Path(__file__).resolve().parent.parent, custom)
        activity.record("settings_changed", "Jarvis will start automatically when you sign in" if enabled
                        else "Jarvis will no longer start automatically")
        return {"supported": True, "enabled": enabled}

    # ------------------------------------------------------------ learn: guides, starter decks, practice
    @app.get("/api/learn/guides")
    def list_guides():
        return guides.list()

    @app.get("/api/learn/guides/{guide_id}")
    def get_guide(guide_id: str):
        return guides.get(guide_id)

    @app.get("/api/offline/pack")
    def offline_pack():
        """What the phone keeps so these work with no connection: the guides, the build planner, the
        hackathon planner and the verses/quotes. No personal data."""
        return {"version": __version__,
                "guides": [guides.get(g["id"]) for g in guides.list()],
                "build": build_catalog.offline_data(), "hackathon": build_hackathon.offline_data(),
                "words": pick_motivation_entries()}

    @app.get("/api/learn/search")
    def search_guides(q: str = ""):
        return [{k: v for k, v in hit.items() if k != "text"} for hit in guides.search(q[:300], k=8)]

    @app.get("/api/learn/decks")
    def list_starter_decks():
        return starter_decks.list()

    @app.post("/api/learn/decks/{key}/install")
    def install_starter_deck(key: str, request: Request):
        result = starter_decks.install(key)
        activity.record("study", f"Added the starter deck '{result['name']}' ({result['added']} new card(s)){via(request)}",
                        deck_id=result["deck_id"])
        return result

    @app.get("/api/learn/exercises")
    def list_exercises(request: Request):
        # Code runs on the device Jarvis runs on: never on the laptop at a phone's request.
        return {**exercise_list(practice, runtimes), "can_run": pocket or not request.scope.get("jarvis.device")}

    @app.get("/api/learn/exercises/{exercise_id}")
    def get_exercise(exercise_id: str):
        return exercise_detail(exercise_id, practice)

    @app.put("/api/learn/exercises/{exercise_id}/code")
    def save_exercise_code(exercise_id: str, body: PracticeCode):
        exercise_bank.by_id(exercise_id)
        practice.save_code(exercise_id, body.code)
        return {"saved": True}

    @app.post("/api/learn/exercises/{exercise_id}/run")
    async def run_exercise(exercise_id: str, body: PracticeCode, request: Request):
        ex = exercise_bank.by_id(exercise_id)
        result = await asyncio.to_thread(run_code, ex, body.code, runtimes)
        if not result.get("unavailable"):
            progress = practice.record(exercise_id, body.code, result)
            result["solved"] = bool(progress.get("solved_at"))
            result["attempts"] = progress.get("attempts", 0)
        activity.record("practice", f"Checked practice '{ex['title']}': {result['passed']}/{result['total']} tests passed"
                        f"{via(request)}", exercise=exercise_id, passed=result["passed"], total=result["total"])
        return result

    @app.post("/api/learn/runtimes/refresh")
    def refresh_runtimes():
        runtimes.refresh()
        return runtimes.summary()

    @app.get("/api/learn/exercises/{exercise_id}/solution")
    def exercise_solution(exercise_id: str):
        ex = exercise_bank.by_id(exercise_id)
        return {"solution": ex["solution"], "language": ex["language"]}

    @app.post("/api/learn/exercises/{exercise_id}/hint")
    async def exercise_hint(exercise_id: str, body: HintRequest):
        ex = exercise_bank.by_id(exercise_id)
        return {"hint": await assistant.practice_hint(ex, body.code, body.results, body.question)}

    @app.get("/api/learn/standup")
    def get_standup():
        return standup_note(tasks.list())

    app.include_router(make_api_lab(api_lab))

    # ------------------------------------------------------------ progress and encouragement
    @app.get("/api/progress")
    def get_progress(days: int = 30):
        return progress_report(db, days)

    # ------------------------------------------------------------ check-ins (how you feel before a session)
    @app.get("/api/checkins")
    def list_checkins(days: int = 30):
        return checkins.since(max(1, min(days, 365)))

    @app.get("/api/checkins/latest")
    def latest_checkin():
        last = checkins.latest()
        return {"checkin": last, "advice": checkin_advice(last) if last else None}

    @app.post("/api/checkins")
    def add_checkin(body: CheckinIn, request: Request):
        row = checkins.add(body)
        activity.record("checkin", f"Checked in: mood {body.mood}/5, energy {body.energy}/5, stress {body.stress}/5{via(request)}")
        return {"checkin": row, "advice": checkin_advice(row)}

    @app.get("/api/checkins/insights")
    def get_checkin_insights(days: int = 60):
        return checkin_insights(db, max(7, min(days, 365)))

    # ------------------------------------------------------------ Coding Focus and Study Buddy over other apps
    @app.get("/api/focus")
    def get_focus():
        return {**focus.status(), "recent_apps": focus.recent_apps(), "platform": sys.platform}

    @app.put("/api/focus")
    def put_focus(body: FocusSettings):
        changes = {k: v for k, v in body.model_dump().items() if v is not None}
        if "focus_apps" in changes:
            changes["focus_apps"] = sorted({a.strip().lower() for a in changes["focus_apps"] if a.strip()})
        config.update(changes)
        if "focus_enabled" in changes:
            activity.record("settings_changed", "Coding Focus turned " + ("on" if changes["focus_enabled"] else "off"))
        focus.tick()
        return focus.status()

    @app.post("/api/focus/snooze")
    def snooze_focus(body: SnoozeRequest):
        focus.snooze(body.minutes)
        if body.break_:
            break_until["t"] = time.time() + body.minutes * 60
        return focus.status()

    @app.post("/api/focus/pause")
    def pause_focus():
        focus.pause(True)
        return focus.status()

    @app.post("/api/focus/resume")
    def resume_focus():
        focus.pause(False)
        break_until["t"] = 0.0
        return focus.status()

    @app.post("/api/focus/heartbeat")
    def focus_heartbeat():
        focus.heartbeat()  # the Jarvis tab is in front: studying in Jarvis counts as focus
        return {"ok": True}

    @app.put("/api/companion/overlay")
    def put_overlay(body: OverlayRequest):
        changes = {}
        if body.enabled is not None:
            changes["overlay_enabled"] = body.enabled
        if body.pack:
            changes["overlay_pack"] = body.pack
        s = config.update(changes)
        if s.overlay_enabled and not pocket:
            overlay.start()
        else:
            overlay.stop()
        return {"enabled": s.overlay_enabled, "pack": s.overlay_pack, "supported": overlay.supported, "running": overlay.running()}

    @app.put("/api/companion/session")
    def put_page_pose(body: PageCompanion):
        """The open Jarvis page reports Study Buddy's pose (and a reminder), so the floating window matches."""
        if body.message and body.message != page_pose["message"]:
            page_pose["seq"] += 1
        page_pose.update(pose=body.pose, at=time.time(), message=body.message)
        return {"ok": True}

    @app.get("/api/companion/state")
    def companion_state():
        """The pose for Study Buddy's floating window (and anything else that wants it), from Coding Focus and recent events."""
        s = config.get()
        f = focus.status()
        now = time.time()
        pose, message = "study", None
        success = None
        with db.connect() as conn:
            row = conn.execute("SELECT id, details, created_at FROM actions WHERE kind = 'practice' ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            try:
                d = json.loads(row["details"] or "{}")
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])).total_seconds()
                if d.get("total") and d.get("passed") == d.get("total") and age < 20:
                    success = {"id": f"s{row['id']}", "text": "All tests pass! \u2728 That's real progress.", "alert": False}
            except (ValueError, TypeError):
                pass
        hour = datetime.now().hour
        if f["state"] == "distracted":
            pose = "pouty"
            if f["alert"]:
                message = {"id": f"a{f['alert']['id']}", "text": f["alert"]["message"], "alert": True}
        elif success:
            pose, message = "celebrate", success
        elif now < break_until["t"]:
            pose = "sleepy"
            message = {"id": f"b{int(break_until['t'])}", "text": "Break time! Stretch, drink water, rest your eyes. \u2615", "alert": False}
        elif f["state"] in ("snoozed", "paused"):
            pose = "sleepy"
        elif f["state"] == "coding":
            pose = "code"
        elif f["state"] == "away":
            pose = "idea"
        elif hour >= 23 or hour < 5:
            pose = "sleepy"
        if now - page_pose["at"] < 25 and page_pose["pose"]:  # the Jarvis page is open: show what it shows
            pose = page_pose["pose"]
            if page_pose["message"]:
                message = {"id": f"p{page_pose['seq']}", "text": page_pose["message"], "alert": pose == "pouty"}
        return {"pack": s.overlay_pack, "pose": pose, "message": message, "overlay": s.overlay_enabled, "focus": f}

    # ------------------------------------------------------------ build: stack planner, catalog, hackathon
    @app.get("/api/build/catalog")
    def get_catalog():
        return {"tech": list(build_catalog.TECH.values()),
                "blueprints": [{"id": b["id"], "title": b["title"]} for b in build_catalog.BLUEPRINTS]}

    @app.post("/api/build/plan")
    def build_plan(body: PlanRequest):
        return build_catalog.plan(body.idea, body.language)

    @app.post("/api/build/hackathon")
    def build_hackathon_plan(body: HackathonRequest, request: Request):
        try:
            plan = build_hackathon.plan(body.name, body.start, body.hours, body.team, body.theme, body.criteria or None)
        except ValueError:
            raise HTTPException(400, "Start must be a date and time like 2026-10-24T09:00.")
        if body.add_tasks:
            parent = tasks.create(TaskIn(title=f"Hackathon: {plan['name']}", area="dev", priority="high",
                                         due_date=plan["end"][:10], description=plan["theme"]))
            for t in build_hackathon.tasks(plan):
                tasks.create(TaskIn(title=t["title"], description=t["description"], due_date=t["due"],
                                    parent_id=parent["id"], area="dev"))
            activity.record("task_created", f"Planned the hackathon '{plan['name']}' as tasks{via(request)}", task_id=parent["id"])
            plan["task_id"] = parent["id"]
        return plan

    @app.get("/api/motivation")
    def get_motivation(kinds: str = "both", focus: str = "", exclude: str = ""):
        return pick_motivation(db, kinds=kinds, focus=focus, exclude=[x for x in exclude.split(",") if x][:40])

    # ------------------------------------------------------------ activity
    @app.get("/api/activity")
    def list_activity(scope: str = "session"):
        return activity.list(current_session_only=scope != "all")

    return app
