"""Workspace sandboxing, secret protection, search, change proposals and commands."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from jarvis.activity import ActivityLog
from jarvis.db import Database
from jarvis.project.changes import ChangeError, ChangeManager
from jarvis.project.commands import CommandError, CommandRunner, classify, detect_presets, split_command
from jarvis.project.index import ProjectIndex, tokenize
from jarvis.project.secrets import is_sensitive_path, redact
from jarvis.project.workspace import AccessDenied, Workspace


# ------------------------------------------------------------------ workspace
def test_paths_outside_project_are_refused(project, tmp_path):
    ws = Workspace(project)
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    for bad in ["../outside.txt", "src/../../outside.txt", str(outside)]:
        with pytest.raises(AccessDenied):
            ws.read_text(bad)
    assert "def add" in ws.read_text("src/calculator.py")
    assert "def add" in ws.read_text("src\\calculator.py")


def test_symlink_escape_is_refused(project, tmp_path):
    target = tmp_path / "secret-dir"
    target.mkdir()
    (target / "data.txt").write_text("outside data")
    link = project / "link"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("Creating symlinks needs extra permissions on this system")
        import _winapi  # directory junctions need no admin rights on Windows
        _winapi.CreateJunction(str(target), str(link))
    ws = Workspace(project)
    with pytest.raises(AccessDenied):
        ws.read_text("link/data.txt")
    assert "link" not in [e["name"] for e in ws.list_dir("")]


def test_refuses_drive_root_and_home():
    with pytest.raises(AccessDenied):
        Workspace(Path(Path.home().anchor))
    with pytest.raises(AccessDenied):
        Workspace(Path.home())
    with pytest.raises(FileNotFoundError):
        Workspace(Path.home() / "definitely-not-a-real-folder-jarvis")


def test_secret_files_hidden_everywhere(project):
    ws = Workspace(project)
    with pytest.raises(AccessDenied):
        ws.read_text(".env")
    with pytest.raises(AccessDenied):
        ws.read_text("id_rsa")
    listed = {e["name"]: e for e in ws.list_dir("")}
    assert listed[".env"]["sensitive"] and listed["id_rsa"]["sensitive"]
    files = set(ws.iter_files())
    assert ".env" not in files and "id_rsa" not in files and "src/calculator.py" in files


@pytest.mark.parametrize("path,sensitive", [
    (".env", True), (".env.local", True), (".env.example", False), ("prod.env", True), ("server.pem", True),
    ("keys/id_ed25519", True), (".aws/config", True), ("app/.ssh/known_hosts", True), ("credentials.json", True),
    ("secrets.yaml", True), ("secrets.py", True), ("terraform.tfstate", True), ("my_api_key.txt", True),
    ("src/credential_service.py", False), ("src/tokenizer.py", False), ("README.md", False),
    ("src/secret_santa.py", False), ("config/db_credentials.yml", True),
])
def test_sensitive_name_rules(path, sensitive):
    assert bool(is_sensitive_path(path)) is sensitive


def test_user_exclude_patterns(project):
    ws = Workspace(project, extra_exclude=["tests/*", "*.md"])
    with pytest.raises(AccessDenied):
        ws.read_text("README.md")
    with pytest.raises(AccessDenied):
        ws.read_text("tests/test_calculator.py")
    ws.read_text("src/calculator.py")


def test_redaction():
    text = (
        'password = "letmein123"\n'
        'token: "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"\n'
        "aws = AKIAABCDEFGHIJKLMNOP\n"
        "url = postgres://admin:hunter2pass@localhost/db\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----\n"
        'password = get_password()\n'
        'api_key = "${API_KEY}"\n'
    )
    out, n = redact(text)
    for secret in ["letmein123", "ghp_abcdef", "AKIAABCDEFGHIJKLMNOP", "hunter2pass", "MIIabc"]:
        assert secret not in out
    assert "get_password()" in out and "${API_KEY}" in out
    assert n == 5


def test_binary_and_large_files_refused(project):
    (project / "image.png").write_bytes(b"\x89PNG\x00\x00")
    (project / "big.txt").write_text("x" * 50_000)
    ws = Workspace(project, max_file_bytes=10_000)
    with pytest.raises(AccessDenied):
        ws.read_text("image.png")
    with pytest.raises(AccessDenied):
        ws.read_text("big.txt")


# ------------------------------------------------------------------ index
def test_tokenize_splits_identifiers():
    toks = tokenize("getUserName parse_http_response")
    assert {"getusername", "get", "user", "name", "parse_http_response", "parse", "http", "response"} <= set(toks)


def test_index_finds_relevant_chunk(project):
    ws = Workspace(project)
    idx = ProjectIndex()
    status = idx.build(ws, max_files=100)
    assert status.state == "ready" and status.files_indexed >= 4
    hits = idx.search("divide by zero")
    assert hits and hits[0]["path"] == "src/calculator.py"
    assert all(".env" not in h["path"] for h in idx.search("API_KEY secret value"))


def test_index_respects_file_limit(project):
    for i in range(10):
        (project / f"extra_{i}.txt").write_text(f"file {i}")
    status = ProjectIndex().build(Workspace(project), max_files=3)
    assert status.files_indexed == 3 and status.limit_reached


# ------------------------------------------------------------------ changes
@pytest.fixture
def changes(data_dir):
    db = Database(data_dir / "jarvis.db")
    return ChangeManager(db, data_dir, ActivityLog(db))


def test_create_apply_undo(project, changes):
    ws = Workspace(project)
    p = changes.propose(ws, "src/new_module/util.py", "def hello():\n    return 'hi'\n")
    assert p["kind"] == "create" and p["status"] == "pending"
    assert "+def hello" in p["diff"]
    assert any(w["code"] == "new_folders" for w in p["warnings"])
    assert not (project / "src/new_module/util.py").exists()  # nothing written before approval
    changes.apply(ws, p["id"])
    assert (project / "src/new_module/util.py").read_text() == "def hello():\n    return 'hi'\n"
    changes.undo(ws, p["id"])
    assert not (project / "src/new_module/util.py").exists()


def test_modify_keeps_backup_and_line_endings(project, changes):
    target = project / "src" / "crlf.py"
    target.write_bytes(b"a = 1\r\nb = 2\r\n")
    ws = Workspace(project)
    p = changes.propose(ws, "src/crlf.py", "a = 1\nb = 3\n")
    assert "-b = 2" in p["diff"] and "+b = 3" in p["diff"]
    applied = changes.apply(ws, p["id"])
    assert target.read_bytes() == b"a = 1\r\nb = 3\r\n"
    assert Path(applied["backup_path"]).read_bytes() == b"a = 1\r\nb = 2\r\n"
    changes.undo(ws, p["id"])
    assert target.read_bytes() == b"a = 1\r\nb = 2\r\n"


def test_apply_refuses_if_file_changed_meanwhile(project, changes):
    ws = Workspace(project)
    p = changes.propose(ws, "README.md", "# New readme\n")
    (project / "README.md").write_text("# Someone edited this\n")
    with pytest.raises(ChangeError, match="changed after"):
        changes.apply(ws, p["id"])
    assert changes.get(p["id"])["status"] == "conflict"
    assert (project / "README.md").read_text() == "# Someone edited this\n"


def test_risky_changes_need_confirmation(project, changes):
    ws = Workspace(project)
    big = "\n".join(f"line_{i} = {i}" for i in range(40)) + "\n"
    (project / "big.py").write_text(big)
    p = changes.propose(ws, "big.py", "line_0 = 0\n# ... existing code ...\n")
    codes = {w["code"] for w in p["warnings"]}
    assert {"large_overwrite", "placeholder"} <= codes and p["needs_confirm"]
    with pytest.raises(ChangeError, match="confirm"):
        changes.apply(ws, p["id"])
    assert (project / "big.py").read_text() == big
    changes.apply(ws, p["id"], confirmed=True)
    assert "existing code" in (project / "big.py").read_text()


def test_snippet_over_small_file_warns(project, changes):
    # A model's 2-line snippet proposed as a whole 8-line file would silently delete the rest.
    p = changes.propose(Workspace(project), "src/calculator.py", "def divide(a, b):\n    return a / b\n")
    assert any(w["code"] == "large_overwrite" for w in p["warnings"]) and p["needs_confirm"]


def test_redacted_marker_warning_and_secret_paths(project, changes):
    ws = Workspace(project)
    p = changes.propose(ws, "settings.py", 'password = "[REDACTED]"\n')
    assert any(w["code"] == "redacted" for w in p["warnings"])
    with pytest.raises(AccessDenied):
        changes.propose(ws, ".env", "API_KEY=x\n")
    with pytest.raises(AccessDenied):
        changes.propose(ws, "../escape.txt", "x")
    with pytest.raises(AccessDenied):
        changes.propose(ws, ".git/config", "x")


def test_delete_requires_confirmation_and_can_be_undone(project, changes):
    ws = Workspace(project)
    p = changes.propose(ws, "README.md", None)
    assert p["kind"] == "delete" and p["needs_confirm"]
    changes.apply(ws, p["id"], confirmed=True)
    assert not (project / "README.md").exists()
    changes.undo(ws, p["id"])
    assert (project / "README.md").read_text().startswith("# Sample")


def test_identical_content_and_reject(project, changes):
    ws = Workspace(project)
    with pytest.raises(ChangeError, match="identical"):
        changes.propose(ws, "README.md", (project / "README.md").read_text())
    p = changes.propose(ws, "README.md", "# changed\n")
    changes.reject(p["id"])
    with pytest.raises(ChangeError):
        changes.apply(ws, p["id"])


def test_undo_refuses_when_edited_after_apply(project, changes):
    ws = Workspace(project)
    p = changes.propose(ws, "README.md", "# v2\n")
    changes.apply(ws, p["id"])
    (project / "README.md").write_text("# v3 by hand\n")
    with pytest.raises(ChangeError, match="edited after"):
        changes.undo(ws, p["id"])
    changes.undo(ws, p["id"], force=True)
    assert (project / "README.md").read_text().startswith("# Sample")


# ------------------------------------------------------------------ commands
def test_split_command():
    assert split_command('pytest -k "a and b"') == ["pytest", "-k", "a and b"]
    assert split_command(r"C:\tools\x.exe tests\unit") == [r"C:\tools\x.exe", r"tests\unit"]
    for bad in ["echo hi && rm -rf /", "git log | head", "pytest > out.txt", "a; b", "", "x\ny"]:
        with pytest.raises(CommandError):
            split_command(bad)


@pytest.mark.parametrize("command,level", [
    ("git status", "safe"), ("git diff --stat", "safe"), ("node --version", "safe"),
    ("rm -rf build", "danger"), ("del /s *.py", "danger"), ("pip install requests", "danger"),
    ("python -m pip install flask", "danger"), ("npm install", "danger"), ("npx create-react-app x", "danger"),
    ("curl https://example.com", "danger"), ("git push origin main", "danger"), ("git reset --hard", "danger"),
    ("python manage.py migrate", "danger"), ("alembic upgrade head", "danger"), ("python -c print(1)", "danger"),
    ("powershell -Command Get-Process", "danger"), ("shutdown /s", "danger"), ("reg add HKCU\\x", "danger"),
    ("cargo test", "caution"), ("go test ./...", "caution"), ("mytool --flag", "caution"),
    ("python script.py", "caution"),
])
def test_command_classification(command, level):
    assert classify(split_command(command))["level"] == level


def test_presets_detected_and_trusted(project):
    ws = Workspace(project)
    presets = detect_presets(ws)
    cmd = next(p for p in presets if p["label"] == "Python: run tests")
    assert cmd["command"].endswith("-m pytest -q")
    assert classify(cmd["argv"], presets)["level"] == "safe"
    (project / "package.json").write_text('{"scripts": {"test": "jest", "build": "vite build"}}')
    labels = {p["command"] for p in detect_presets(ws)}
    assert {"npm test", "npm run build"} <= labels


def _wait(run, timeout=30):
    end = time.time() + timeout
    while run.status == "running" and time.time() < end:
        time.sleep(0.05)
    return run


def test_runner_runs_in_project_and_captures_output(project):
    runner = CommandRunner()
    ws = Workspace(project)
    script = project / "show_cwd.py"
    script.write_text("import os\nprint('cwd=' + os.getcwd())\nraise SystemExit(3)\n")
    run = _wait(runner.start("python show_cwd.py", [sys.executable, "show_cwd.py"], ws, "caution", timeout=30))
    assert run.status == "failed" and run.exit_code == 3
    assert f"cwd={project}" in run.output


def test_runner_cancel_and_timeout(project):
    runner = CommandRunner()
    ws = Workspace(project)
    (project / "sleepy.py").write_text("import time\nprint('start', flush=True)\ntime.sleep(60)\n")
    run = runner.start("python sleepy.py", [sys.executable, "sleepy.py"], ws, "caution", timeout=60)
    time.sleep(0.8)
    runner.cancel(run.id)
    assert _wait(run, 15).status == "cancelled"
    run2 = _wait(runner.start("python sleepy.py", [sys.executable, "sleepy.py"], ws, "caution", timeout=1), 20)
    assert run2.status == "timed_out"


def test_runner_rejects_missing_program_and_outside_paths(project):
    runner = CommandRunner()
    ws = Workspace(project)
    with pytest.raises(CommandError, match="not installed"):
        runner.start("nonexistent-tool-xyz", ["nonexistent-tool-xyz"], ws, "caution", 10)
    with pytest.raises(AccessDenied):
        runner.start("../evil.exe", ["../evil.exe"], ws, "caution", 10)
