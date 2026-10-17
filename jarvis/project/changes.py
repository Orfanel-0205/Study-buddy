"""Reviewable file changes.

Nothing is written to your project until you approve it:

1. propose()  -> stores the change and shows you a diff plus warnings
2. apply()    -> backs up the original, then writes (refuses if the file
                 changed since the proposal, or if a warning needs your OK)
3. undo()     -> restores the backup (or removes a file Jarvis created)
4. reject()   -> discards the proposal

Backups live in <data folder>/backups/<proposal id>/.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

from ..activity import ActivityLog
from ..db import Database, now_iso
from .workspace import AccessDenied, Workspace

MAX_CONTENT = 2_000_000
MAX_DIFF_CHARS = 200_000

_PLACEHOLDERS = re.compile(
    r"""(?imx)
    ^\s*(?://|\#|/\*|<!--|--|;)\s*\.\.\.\s*(?:\*/|-->)?\s*$             # a comment that is only "..."
    | \.\.\.\s*(?:existing|rest\ of|remaining|other|previous|same\ as\ before|unchanged)
    | (?:rest\ of\ (?:the\ )?(?:code|file|implementation)|existing\ code)\s*(?:here|unchanged|remains|stays|goes\ here|\.\.\.)
    | \((?:unchanged|same\ as\ before)\)
    """
)


class ChangeError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


class ChangeManager:
    def __init__(self, db: Database, data_dir: Path, activity: ActivityLog):
        self.db = db
        self.backup_root = data_dir / "backups"
        self.activity = activity

    # ------------------------------------------------------------ propose
    def propose(self, ws: Workspace, rel_path: str, new_content: str | None, *,
                source: str = "assistant", note: str = "") -> dict:
        """new_content=None means 'delete this file'."""
        path = ws.check_writable(rel_path)
        rel = ws.rel(path)
        kind = "delete" if new_content is None else ("modify" if path.exists() else "create")
        warnings: list[dict] = []
        original_text = ""
        original_hash = ""
        if path.exists():
            if path.is_dir():
                raise ChangeError(f"'{rel}' is a folder. Jarvis only changes individual files.")
            raw = path.read_bytes()
            original_hash = _sha(raw)
            if kind != "delete":
                if b"\x00" in raw[:8192]:
                    raise ChangeError(f"'{rel}' is a binary file; Jarvis only edits text files.")
                original_text = _normalize(raw.decode("utf-8-sig", errors="replace"))
        elif kind == "delete":
            raise ChangeError(f"'{rel}' does not exist, so there is nothing to delete.")

        if new_content is not None:
            if len(new_content) > MAX_CONTENT:
                raise ChangeError("The new content is too large (over 2 MB).")
            new_text = _normalize(new_content)
            if new_text and not new_text.endswith("\n"):
                new_text += "\n"
            if kind == "modify" and new_text == original_text:
                raise ChangeError(f"The proposed content is identical to the current '{rel}'. Nothing to change.")
            warnings += self._content_warnings(original_text, new_text, kind)
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            if missing:
                warnings.append({"code": "new_folders", "needs_confirm": False,
                                 "message": "New folder(s) will be created: " + ", ".join(ws.rel(m) for m in reversed(missing))})
        else:
            new_text = None
            warnings.append({"code": "delete", "needs_confirm": True,
                             "message": f"This permanently deletes '{rel}' from your project (a backup is kept so you can undo)."})

        diff = self._diff(rel, original_text if kind != "create" else "", new_text or "", kind, path)
        now = now_iso()
        with self.db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO proposals (project_root, path, kind, new_content, original_exists,
                   original_hash, diff, warnings, note, source, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (str(ws.root), rel, kind, new_text, int(path.exists()), original_hash, diff,
                 json.dumps(warnings), note[:2000], source, now, now),
            )
            pid = cur.lastrowid
        self.activity.record("change_proposed", f"Proposed to {kind} {rel}", proposal_id=pid,
                             path=rel, source=source)
        return self.get(pid)

    @staticmethod
    def _content_warnings(original: str, new: str, kind: str) -> list[dict]:
        warnings = []
        if _PLACEHOLDERS.search(new) and not _PLACEHOLDERS.search(original):
            warnings.append({"code": "placeholder", "needs_confirm": True, "message":
                             "The new content contains placeholder text like '... existing code ...'. "
                             "Applying it would replace your real code with that placeholder. Ask Jarvis "
                             "for the complete file, or edit it before applying."})
        if "[REDACTED" in new and "[REDACTED" not in original:
            warnings.append({"code": "redacted", "needs_confirm": True, "message":
                             "The new content contains [REDACTED] markers where secrets were hidden from "
                             "the model. Applying it would overwrite your real values."})
        if kind == "modify":
            old_lines = original.splitlines()
            matcher = difflib.SequenceMatcher(None, old_lines, new.splitlines(), autojunk=False)
            kept = sum(block.size for block in matcher.get_matching_blocks())
            removed = len(old_lines) - kept
            # e.g. a 4-line snippet proposed over a 17-line file would silently drop most of it
            if removed >= 5 and removed / max(len(old_lines), 1) >= 0.4:
                warnings.append({"code": "large_overwrite", "needs_confirm": True, "message":
                                 f"This replaces {removed} of {len(old_lines)} existing lines "
                                 f"({round(100 * removed / len(old_lines))}%). Check the diff carefully."})
        return warnings

    @staticmethod
    def _diff(rel: str, old: str, new: str, kind: str, path: Path) -> str:
        if kind == "delete":
            try:
                old = _normalize(path.read_bytes().decode("utf-8-sig", errors="replace"))
            except OSError:
                old = ""
            if "\x00" in old[:8192]:
                return f"(binary file {rel} will be deleted)"
        lines = difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="/dev/null" if kind == "create" else f"a/{rel}",
            tofile="/dev/null" if kind == "delete" else f"b/{rel}", n=3)
        text = "".join(line if line.endswith("\n") else line + "\n" for line in lines)
        if len(text) > MAX_DIFF_CHARS:
            text = text[:MAX_DIFF_CHARS] + "\n... (diff truncated for display) ...\n"
        return text

    # ------------------------------------------------------------ queries
    def get(self, pid: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (pid,)).fetchone()
        if not row:
            raise ChangeError(f"Change #{pid} does not exist.")
        data = dict(row)
        data["warnings"] = json.loads(data["warnings"] or "[]")
        data["needs_confirm"] = any(w["needs_confirm"] for w in data["warnings"])
        return data

    def list(self, *, project_root: str | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
        query, params = "SELECT id FROM proposals WHERE 1=1", []
        if project_root:
            query += " AND project_root = ?"
            params.append(project_root)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            ids = [r[0] for r in conn.execute(query, params).fetchall()]
        items = [self.get(i) for i in ids]
        for item in items:
            item.pop("new_content", None)  # keep list responses small
        return items

    def _set(self, pid: int, **fields) -> None:
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db.connect() as conn:
            conn.execute(f"UPDATE proposals SET {cols} WHERE id = ?", (*fields.values(), pid))

    def _workspace_check(self, ws: Workspace | None, prop: dict) -> Workspace:
        if ws is None or str(ws.root) != prop["project_root"]:
            raise ChangeError("This change belongs to a different project. Open that project first.")
        return ws

    # ------------------------------------------------------------ actions
    def apply(self, ws: Workspace | None, pid: int, *, confirmed: bool = False) -> dict:
        prop = self.get(pid)
        ws = self._workspace_check(ws, prop)
        if prop["status"] != "pending":
            raise ChangeError(f"Change #{pid} is already {prop['status']}.")
        if prop["needs_confirm"] and not confirmed:
            raise ChangeError("This change has warnings you need to confirm before it can be applied.")
        path = ws.check_writable(prop["path"])
        current = path.read_bytes() if path.exists() else None
        current_hash = _sha(current) if current is not None else ""
        if bool(current is not None) != bool(prop["original_exists"]) or current_hash != prop["original_hash"]:
            self._set(pid, status="conflict", error="The file changed after this change was proposed.")
            raise ChangeError(f"'{prop['path']}' changed after this change was proposed, so it was not applied. "
                              "Ask for a fresh proposal based on the current file.")
        backup = ""
        if current is not None:
            backup_dir = self.backup_root / str(pid)
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / (path.name + ".orig")
            backup_path.write_bytes(current)
            backup = str(backup_path)
        try:
            if prop["kind"] == "delete":
                path.unlink()
                written_hash = ""
            else:
                data = self._encode(prop["new_content"] or "", current)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                written_hash = _sha(data)
        except OSError as exc:
            self._set(pid, status="failed", error=str(exc), backup_path=backup)
            self.activity.record("change_failed", f"Could not {prop['kind']} {prop['path']}: {exc}", proposal_id=pid)
            raise ChangeError(f"Could not write '{prop['path']}': {exc}") from exc
        self._set(pid, status="applied", backup_path=backup, written_hash=written_hash, error="")
        self.activity.record("change_applied", f"Applied: {prop['kind']} {prop['path']}", proposal_id=pid,
                             path=prop["path"], backup=backup)
        return self.get(pid)

    @staticmethod
    def _encode(text: str, original: bytes | None) -> bytes:
        """Keep the original file's line endings and BOM so diffs stay clean."""
        if original is not None and b"\r\n" in original:
            text = text.replace("\n", "\r\n")
        data = text.encode("utf-8")
        if original is not None and original.startswith(b"\xef\xbb\xbf"):
            data = b"\xef\xbb\xbf" + data
        return data

    def reject(self, pid: int) -> dict:
        prop = self.get(pid)
        if prop["status"] != "pending":
            raise ChangeError(f"Change #{pid} is already {prop['status']}.")
        self._set(pid, status="rejected")
        self.activity.record("change_rejected", f"Rejected change to {prop['path']}", proposal_id=pid)
        return self.get(pid)

    def undo(self, ws: Workspace | None, pid: int, *, force: bool = False) -> dict:
        prop = self.get(pid)
        ws = self._workspace_check(ws, prop)
        if prop["status"] != "applied":
            raise ChangeError(f"Only applied changes can be undone (this one is {prop['status']}).")
        path = ws.check_writable(prop["path"])
        current = path.read_bytes() if path.exists() else None
        expected_unchanged = (current is None) if prop["kind"] == "delete" else (
            current is not None and _sha(current) == prop["written_hash"])
        if not expected_unchanged and not force:
            raise ChangeError(f"'{prop['path']}' was edited after Jarvis changed it. Undoing would lose "
                              "those edits; confirm to undo anyway.")
        try:
            if prop["original_exists"]:
                backup = Path(prop["backup_path"])
                if not backup.exists():
                    raise ChangeError("The backup for this change is missing, so it can't be undone.")
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(backup, path)
            elif path.exists():
                path.unlink()
        except OSError as exc:
            raise ChangeError(f"Could not undo: {exc}") from exc
        self._set(pid, status="undone")
        self.activity.record("change_undone", f"Undid change to {prop['path']}", proposal_id=pid)
        return self.get(pid)


__all__ = ["ChangeError", "ChangeManager", "AccessDenied"]
