"""Project access: the selected folder, its search index and detected commands."""

from __future__ import annotations

import threading
from dataclasses import asdict

from ..activity import ActivityLog
from ..config import ConfigStore
from ..db import Database
from .commands import detect_presets
from .embeddings import Embedder
from .index import ProjectIndex
from .workspace import AccessDenied, Workspace


class ProjectManager:
    """Holds the currently open project. Only one project is open at a time."""

    def __init__(self, config: ConfigStore, activity: ActivityLog, db: Database | None = None):
        self.config = config
        self.activity = activity
        self.db = db
        self.workspace: Workspace | None = None
        self.index = ProjectIndex()
        self.presets: list[dict] = []
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def open(self, path: str) -> Workspace:
        s = self.config.get()
        ws = Workspace(path, s.extra_exclude_patterns, s.max_file_bytes)
        with self._lock:
            self.index.cancel()
            self.workspace = ws
            self.index = ProjectIndex()
            self.presets = detect_presets(ws)
        recent = [str(ws.root)] + [p for p in s.recent_projects if p != str(ws.root)]
        self.config.update({"last_project": str(ws.root), "recent_projects": recent[:8]})
        self.activity.record("project_opened", f"Opened project {ws.name}", path=str(ws.root))
        self.reindex()
        return ws

    def close(self) -> None:
        with self._lock:
            if self.workspace:
                self.activity.record("project_closed", f"Closed project {self.workspace.name}")
            self.index.cancel()
            self.workspace = None
            self.index = ProjectIndex()
            self.presets = []
        self.config.update({"last_project": ""})

    def reindex(self) -> None:
        ws, index = self.workspace, self.index
        if not ws:
            raise AccessDenied("No project is open.")
        index.cancel()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        settings = self.config.get()
        max_files = settings.max_index_files
        index.status.state = "indexing"

        def run():
            embedder = None
            if settings.semantic_search:
                try:
                    embedder = Embedder(settings, self.db)
                except Exception:  # e.g. a non-local endpoint: keyword search only
                    embedder = None
            status = index.build(ws, max_files, embedder)
            self.activity.record("project_indexed",
                                 f"Indexed {status.files_indexed} files in {ws.name} ({status.state})",
                                 **asdict(status))

        self._thread = threading.Thread(target=run, daemon=True, name="jarvis-indexer")
        self._thread.start()

    def wait_for_index(self, timeout: float = 30) -> None:
        if self._thread:
            self._thread.join(timeout)

    def refresh_presets(self) -> list[dict]:
        if self.workspace:
            self.presets = detect_presets(self.workspace)
        return self.presets
