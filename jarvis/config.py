"""Settings: loaded from and saved to config.json in the Jarvis data folder.

Every option can be changed in the Settings screen. Editing config.json by hand
also works (restart Jarvis afterwards). Unknown keys are ignored and invalid
values fall back to defaults, so a typo never stops Jarvis from starting.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

ProviderName = Literal["ollama", "openai_compatible"]

# Programs that count as "coding" for Coding Focus (Windows executable names, lower case).
DEFAULT_CODING_APPS = [
    "code.exe", "cursor.exe", "antigravity.exe", "windsurf.exe", "devenv.exe", "idea64.exe", "pycharm64.exe",
    "webstorm64.exe", "phpstorm64.exe", "rider64.exe", "sublime_text.exe", "notepad++.exe", "windowsterminal.exe",
    "powershell.exe", "pwsh.exe", "cmd.exe", "mintty.exe", "wt.exe", "studio64.exe", "postman.exe", "heidisql.exe",
    "laragon.exe", "github desktop.exe", "githubdesktop.exe",
]

DEFAULT_ENDPOINTS = {
    "ollama": "http://127.0.0.1:11434",
    "openai_compatible": "http://127.0.0.1:8080/v1",
}


class Settings(BaseModel):
    # Local model
    provider: ProviderName = "ollama"
    endpoint: str = DEFAULT_ENDPOINTS["ollama"]
    model: str = ""  # empty = pick the best installed model automatically
    code_model: str = ""  # for Implementation and Testing & debugging; empty = same as model
    vision_model: str = ""  # reads attached images; empty = the chat model if it can, else the best installed one
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    context_window: int = Field(8192, ge=1024, le=262144)
    max_answer_tokens: int = Field(2048, ge=256, le=32768)  # longest answer (twice this for Detailed)
    think: bool = False  # let "thinking" models reason before answering (slower)
    # For slow devices (the phone): short instructions, fewer guide notes and less history, so the model
    # has less to read before the first word. Measured on the phone: 2,300 tokens took 68-116 s, 280 took 4-9 s.
    lean_prompt: bool = False
    num_threads: int = Field(0, ge=0, le=64)  # CPU threads for the model; 0 = Ollama decides
    request_timeout: int = Field(600, ge=10, le=7200)
    allow_remote_endpoint: bool = False

    # Answers
    detail: Literal["concise", "detailed"] = "concise"

    # Project access
    max_context_chars: int = Field(12000, ge=1000, le=200000)
    max_file_bytes: int = Field(300_000, ge=10_000, le=5_000_000)
    max_index_files: int = Field(4000, ge=50, le=50000)
    extra_exclude_patterns: list[str] = Field(default_factory=list)
    command_timeout: int = Field(600, ge=5, le=7200)
    semantic_search: bool = True  # also search by meaning, using the embedding model if installed
    embedding_model: str = "nomic-embed-text"

    # Interface
    voice_output: bool = False

    # Reliability
    daily_backup: bool = True  # copy jarvis.db to backups/daily once a day, keeping the last 7

    # Sync (used by Jarvis on the phone): the laptop's phone address and this copy's key for it
    sync_url: str = ""
    sync_token: str = ""
    sync_interval: int = Field(60, ge=15, le=3600)

    # Phone (mobile app over your home Wi-Fi; off unless you turn it on)
    phone_access: bool = False
    phone_port: int = Field(8766, ge=1024, le=65535)

    # Coding Focus (Windows: looks only at which app is in front, never at keystrokes or the screen)
    focus_enabled: bool = False
    focus_grace_minutes: int = Field(5, ge=1, le=120)  # time outside coding apps before Study Buddy reacts
    focus_cooldown_minutes: int = Field(15, ge=1, le=240)  # at most one reminder in this time
    focus_apps: list[str] = Field(default_factory=lambda: list(DEFAULT_CODING_APPS))
    overlay_enabled: bool = False  # Study Buddy floats over other apps (Windows)
    overlay_pack: str = Field("study-buddy-2", pattern=r"^study-buddy-\d$")  # which Study Buddy sticker set floats

    # Remembered state
    last_project: str = ""
    recent_projects: list[str] = Field(default_factory=list)

    @field_validator("endpoint")
    @classmethod
    def _strip_endpoint(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Endpoint must look like http://127.0.0.1:11434")
        return v

    @field_validator("extra_exclude_patterns")
    @classmethod
    def _clean_patterns(cls, v: list[str]) -> list[str]:
        return [p.strip() for p in v if p and p.strip()]


def is_loopback_endpoint(url: str) -> bool:
    """True when the URL points at this computer (localhost / 127.x / ::1)."""
    host = (urlparse(url).hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class EndpointNotLocalError(RuntimeError):
    pass


def ensure_local_endpoint(settings: Settings) -> None:
    """Refuse to talk to a model server on another machine unless explicitly allowed.

    This is what keeps prompts, code and files on this computer.
    """
    if settings.allow_remote_endpoint or is_loopback_endpoint(settings.endpoint):
        return
    raise EndpointNotLocalError(
        f"The model endpoint {settings.endpoint} is not on this computer, so Jarvis "
        "will not send anything to it. Use a local address such as "
        "http://127.0.0.1:11434, or turn on 'Allow non-local endpoint' in Settings "
        "if you trust that machine (for example your own home server)."
    )


class ConfigStore:
    """Thread-safe access to config.json."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "config.json"
        self._lock = threading.Lock()
        self._settings = self._load()

    def _load(self) -> Settings:
        if not self.path.exists():
            settings = Settings()
            self._write(settings)
            return settings
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("config.json unreadable (%s); using defaults", exc)
            return Settings()
        if not isinstance(raw, dict):
            return Settings()
        known = {k: v for k, v in raw.items() if k in Settings.model_fields}
        try:
            return Settings(**known)
        except ValidationError as exc:
            # Keep every valid field, reset only the broken ones.
            bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
            log.warning("Invalid settings reset to defaults: %s", ", ".join(sorted(bad)))
            return Settings(**{k: v for k, v in known.items() if k not in bad})

    def _write(self, settings: Settings) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(settings.model_dump(), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self) -> Settings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def update(self, changes: dict) -> Settings:
        """Validate and persist changes. Raises pydantic.ValidationError on bad input."""
        with self._lock:
            merged = self._settings.model_dump()
            merged.update({k: v for k, v in changes.items() if k in Settings.model_fields})
            new = Settings(**merged)
            self._write(new)
            self._settings = new
            return new.model_copy(deep=True)
