"""Running project commands (tests, builds, linters) safely.

* Commands always run inside the selected project folder.
* No shell is used, so pipes (|), redirects (>) and chaining (&&) are refused.
* Each command is classified as safe / caution / danger. Only safe commands
  run with a single click; everything else needs your explicit approval, and
  dangerous ones (deleting, installing, migrations, system changes, network)
  additionally require you to acknowledge the risk.
* Running commands can be stopped at any time, and they time out.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .workspace import Workspace

OUTPUT_LIMIT = 400_000  # characters kept per run (the tail is kept)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
SHELL_OPERATORS = set(";&|<>")


class CommandError(ValueError):
    pass


def split_command(command: str) -> list[str]:
    command = (command or "").strip()
    if not command:
        raise CommandError("The command is empty.")
    if "\n" in command or "\r" in command:
        raise CommandError("Enter a single command on one line.")
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lex.whitespace_split = True
    lex.escape = ""  # keep Windows backslashes as they are
    try:
        argv = list(lex)
    except ValueError as exc:
        raise CommandError(f"Could not understand the command: {exc} (check the quotes).") from exc
    for tok in argv:
        if tok and set(tok) <= SHELL_OPERATORS:
            raise CommandError(
                f"Jarvis runs one program at a time without a shell, so '{tok}' isn't supported. "
                "Run the commands separately instead (no pipes, redirects or &&).")
    return argv


# ---------------------------------------------------------------- risk rules
def _exe_name(arg: str) -> str:
    name = Path(arg.replace("\\", "/")).name.lower()
    for ext in (".exe", ".cmd", ".bat", ".ps1", ".com"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def _has(argv: list[str], *words: str) -> bool:
    lowered = [a.lower() for a in argv[1:]]
    return any(w in lowered for w in words)


DANGER_EXES = {
    # delete
    "rm": "deletes files", "del": "deletes files", "erase": "deletes files",
    "rmdir": "deletes folders", "rd": "deletes folders", "remove-item": "deletes files",
    "shred": "destroys files", "unlink": "deletes files", "mv": "moves/renames files",
    "move": "moves/renames files", "move-item": "moves/renames files",
    # system
    "reg": "changes the Windows registry", "regedit": "changes the Windows registry",
    "sc": "changes Windows services", "netsh": "changes network settings",
    "shutdown": "shuts down or restarts the computer", "format": "formats a disk",
    "diskpart": "changes disk partitions", "bcdedit": "changes boot settings",
    "setx": "changes environment variables permanently", "icacls": "changes file permissions",
    "takeown": "changes file ownership", "chmod": "changes file permissions",
    "chown": "changes file ownership", "sudo": "runs as administrator", "runas": "runs as another user",
    "systemctl": "changes system services", "launchctl": "changes system services",
    "crontab": "schedules system jobs", "schtasks": "schedules system jobs",
    "net": "changes users, shares or services", "wmic": "changes system settings",
    "kill": "stops processes", "taskkill": "stops processes", "stop-process": "stops processes",
    "set-executionpolicy": "changes PowerShell security settings",
    # network
    "curl": "uses the internet", "wget": "uses the internet", "invoke-webrequest": "uses the internet",
    "iwr": "uses the internet", "invoke-restmethod": "uses the internet", "irm": "uses the internet",
    "ssh": "connects to another computer", "scp": "copies files over the network",
    "sftp": "copies files over the network", "ftp": "copies files over the network",
    "rsync": "copies files, possibly over the network", "npx": "may download and run packages from the internet",
    "pnpx": "may download and run packages from the internet", "bunx": "may download and run packages",
    # package managers that always install
    "choco": "installs software", "winget": "installs software", "scoop": "installs software",
    "apt": "installs software", "apt-get": "installs software", "brew": "installs software",
    "dnf": "installs software", "yum": "installs software", "pacman": "installs software",
    "flyway": "runs database migrations", "liquibase": "runs database migrations",
}

INTERPRETER_INLINE = {
    "python": ("-c",), "python3": ("-c",), "py": ("-c",), "node": ("-e", "--eval", "-p"),
    "perl": ("-e",), "ruby": ("-e",), "powershell": ("-c", "-command", "-encodedcommand", "-e"),
    "pwsh": ("-c", "-command", "-encodedcommand", "-e"), "cmd": ("/c", "/k"),
    "bash": ("-c",), "sh": ("-c",), "zsh": ("-c",),
}


def _danger_reasons(argv: list[str]) -> list[str]:
    exe = _exe_name(argv[0])
    args = [a.lower() for a in argv[1:]]
    first = args[0] if args else ""
    reasons: list[str] = []
    if exe in DANGER_EXES:
        reasons.append(f"'{exe}' {DANGER_EXES[exe]}")
    if exe in INTERPRETER_INLINE and any(a in INTERPRETER_INLINE[exe] for a in args):
        reasons.append(f"runs inline code through '{exe}', which can do anything")
    if exe in ("powershell", "pwsh", "cmd", "bash", "sh", "zsh") and not args:
        reasons.append(f"starts an interactive '{exe}' shell")
    if exe in ("powershell", "pwsh") and any(a.endswith(".ps1") for a in args):
        reasons.append("runs a PowerShell script")
    # package installs
    if exe in ("pip", "pip3") and first in ("install", "uninstall", "download"):
        reasons.append("installs or removes Python packages (uses the internet)")
    if exe in ("python", "python3", "py") and args[:2] == ["-m", "pip"] and len(args) > 2 and args[2] in ("install", "uninstall"):
        reasons.append("installs or removes Python packages (uses the internet)")
    if exe in ("npm", "pnpm", "yarn", "bun") and first in (
            "install", "i", "add", "ci", "uninstall", "remove", "rm", "un", "update", "upgrade", "up",
            "publish", "link", "dlx", "exec", "x", "create", "init"):
        reasons.append(f"'{exe} {first}' installs/changes packages or uses the internet")
    if exe == "yarn" and not args:
        reasons.append("'yarn' with no arguments installs packages")
    if exe in ("cargo",) and first in ("install", "add", "remove", "publish", "update"):
        reasons.append("changes Rust packages (uses the internet)")
    if exe == "go" and first in ("get", "install", "clean"):
        reasons.append("downloads or removes Go packages")
    if exe in ("gem", "composer", "conda", "mamba", "poetry", "pipenv", "uv") and first in (
            "install", "add", "remove", "uninstall", "require", "update", "lock", "sync", "publish"):
        reasons.append(f"'{exe} {first}' installs/changes packages (uses the internet)")
    if exe == "dotnet" and first in ("add", "remove", "nuget", "tool", "new", "workload"):
        reasons.append("changes .NET packages or tools")
    if exe in ("docker", "podman") and first in ("rm", "rmi", "push", "pull", "login", "system", "volume", "prune", "run", "compose"):
        reasons.append(f"'{exe} {first}' changes containers/images or uses the network")
    # git
    if exe == "git":
        if first in ("push", "pull", "fetch", "clone", "submodule"):
            reasons.append(f"'git {first}' uses the network")
        if first == "clean":
            reasons.append("'git clean' permanently deletes untracked files")
        if first == "reset" and "--hard" in args:
            reasons.append("'git reset --hard' throws away uncommitted changes")
        if first in ("checkout", "restore") and ("--" in args or "." in args):
            reasons.append(f"'git {first}' can throw away uncommitted changes")
        if first == "branch" and ("-d" in args or "--delete" in args):
            reasons.append("deletes a git branch")
        if first in ("rebase", "filter-branch", "gc", "prune") or (
                first == "stash" and ("drop" in args or "clear" in args)):
            reasons.append(f"'git {first}' rewrites or removes history/stashes")
        if first == "remote" and any(a in ("add", "remove", "set-url", "rm") for a in args):
            reasons.append("changes git remotes")
    if _is_migration(exe, args):
        reasons.append("runs database migrations (changes your database)")
    if exe == "make" and any(a in ("clean", "install", "deploy", "publish", "release", "distclean") for a in args):
        reasons.append(f"'make {first}' usually deletes, installs or deploys")
    return reasons


def _is_migration(exe: str, args: list[str]) -> bool:
    joined = " ".join(args)
    first = args[0] if args else ""
    if any(a.endswith("manage.py") for a in [exe, *args]) and any(
            a in ("migrate", "flush", "sqlflush", "reset_db") for a in args):
        return True
    if exe == "alembic" and first in ("upgrade", "downgrade", "stamp"):
        return True
    if (exe == "prisma" or "prisma" in args) and any(a in ("migrate", "db") for a in args):
        return True
    if exe in ("rails", "rake") and any(a.startswith("db:") for a in args):
        return True
    if exe in ("knex", "sequelize", "typeorm", "dbmate", "goose", "migrate") and (
            "migrate" in joined or "up" in args or "down" in args):
        return True
    return (exe == "artisan" or "artisan" in args) and "migrate" in joined


def _caution_reasons(argv: list[str]) -> list[str]:
    exe = _exe_name(argv[0])
    args = [a.lower() for a in argv[1:]]
    first = args[0] if args else ""
    if exe in ("mvn", "mvnw", "gradle", "gradlew") or (exe == "cargo" and first in ("build", "test", "check", "run", "clippy")) \
            or (exe == "go" and first in ("build", "test", "vet", "run", "mod")) \
            or (exe == "dotnet" and first in ("build", "test", "run", "restore")):
        return [f"'{exe}' may download missing dependencies from the internet"]
    return []


SAFE_EXACT = [
    ["git", "status"], ["git", "diff"], ["git", "log"], ["git", "show"], ["git", "branch"],
    ["git", "remote", "-v"],
]
SAFE_VERSION_FLAGS = {"--version", "-v", "-V", "version", "--help", "-h"}


def classify(argv: list[str], presets: list[dict] | None = None) -> dict:
    """Return {'level': safe|caution|danger, 'reasons': [...], 'summary': str}."""
    danger = _danger_reasons(argv)
    if danger:
        return {"level": "danger", "reasons": danger,
                "summary": "This command can change or delete things, install software, or use the internet. "
                           "Only run it if you understand and want that."}
    norm = [a.lower() for a in argv]
    for preset in presets or []:
        if preset.get("argv") and [a.lower() for a in preset["argv"]] == norm:
            level = preset.get("level", "safe")
            return {"level": level, "reasons": preset.get("reasons", []), "summary": preset["explanation"]}
    caution = _caution_reasons(argv)
    if caution:
        return {"level": "caution", "reasons": caution,
                "summary": "This command builds or tests the project but may need the internet for dependencies."}
    exe = _exe_name(argv[0])
    if len(argv) == 2 and argv[1] in SAFE_VERSION_FLAGS:
        return {"level": "safe", "reasons": [], "summary": f"Shows the version or help for '{exe}'. It changes nothing."}
    if any(norm[:len(s)] == s and (len(s) > 1) for s in SAFE_EXACT) and not _danger_reasons(argv):
        if not (norm[:2] == ["git", "branch"] and len(norm) > 2):
            return {"level": "safe", "reasons": [], "summary": "Read-only git command: it shows information and changes nothing."}
    return {"level": "caution", "reasons": ["Jarvis does not recognize this command"],
            "summary": "It will run inside your project folder with your user permissions. "
                       "Make sure you know what it does before approving."}


# ---------------------------------------------------------------- presets
def _python_for(ws: Workspace) -> str:
    for candidate in (".venv/Scripts/python.exe", "venv/Scripts/python.exe", ".venv/bin/python", "venv/bin/python"):
        if (ws.root / candidate).exists():
            return candidate.replace("/", os.sep) if os.name == "nt" else candidate
    return "python" if shutil.which("python") else ("python3" if shutil.which("python3") else "python")


def detect_presets(ws: Workspace) -> list[dict]:
    """Find the usual test/build/lint commands for this project."""
    presets: list[dict] = []

    def add(label, command, explanation, level="safe", reasons=None, category="test"):
        presets.append({
            "id": f"p{len(presets) + 1}", "label": label, "command": command,
            "argv": split_command(command), "explanation": explanation,
            "level": level, "reasons": reasons or [], "category": category,
        })

    root = ws.root
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8-sig")).get("scripts", {}) or {}
        except (OSError, ValueError):
            scripts = {}
        pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        note = "" if (root / "node_modules").exists() else (
            " Dependencies don't seem to be installed yet (no node_modules folder), so it may fail until you "
            f"run '{pm} install' (needs internet; Jarvis will ask first).")
        for script, category, what in [
            ("test", "test", "Runs the project's automated tests"),
            ("build", "build", "Builds the project (compiles/bundles it)"),
            ("lint", "lint", "Checks the code for style problems and likely bugs"),
            ("typecheck", "lint", "Checks TypeScript types without producing output"),
            ("type-check", "lint", "Checks TypeScript types without producing output"),
            ("check", "lint", "Runs the project's checks"),
        ]:
            if script in scripts:
                cmd = f"{pm} test" if script == "test" and pm == "npm" else f"{pm} run {script}"
                add(f"{pm}: {script}", cmd,
                    f"{what} using the '{script}' script defined in package.json "
                    f"(`{scripts[script]}`).{note}", category=category)

    py_markers = [root / n for n in ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini", "tox.ini", "requirements.txt")]
    has_py_tests = any(root.glob("test_*.py")) or any(root.glob("tests/**/test_*.py")) or any(root.glob("tests/**/*_test.py"))
    if any(p.exists() for p in py_markers) or has_py_tests:
        py = _python_for(ws)
        if has_py_tests or (root / "pytest.ini").exists():
            add("Python: run tests", f"{py} -m pytest -q",
                "Runs the Python tests with pytest (the project's code will be executed). "
                "Requires pytest to be installed in that Python environment.")
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace") if (root / "pyproject.toml").exists() else ""
        if "[tool.ruff" in pyproject or (root / "ruff.toml").exists() or (root / ".ruff.toml").exists():
            add("Python: lint (ruff)", f"{py} -m ruff check .", "Checks the Python code for common mistakes with ruff.", category="lint")
        if "[tool.mypy" in pyproject or (root / "mypy.ini").exists():
            add("Python: type check (mypy)", f"{py} -m mypy .", "Checks Python type hints with mypy.", category="lint")

    net = ["may download missing dependencies from the internet"]
    if (root / "Cargo.toml").exists():
        add("Rust: test", "cargo test", "Compiles and runs the Rust tests.", "caution", net)
        add("Rust: build", "cargo build", "Compiles the Rust project.", "caution", net, "build")
    if (root / "go.mod").exists():
        add("Go: test", "go test ./...", "Compiles and runs all Go tests.", "caution", net)
        add("Go: vet", "go vet ./...", "Reports suspicious Go code.", "caution", net, "lint")
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        add(".NET: build", "dotnet build", "Compiles the .NET project.", "caution", net, "build")
        add(".NET: test", "dotnet test", "Builds and runs the .NET tests.", "caution", net)
    if (root / "pom.xml").exists():
        mvn = "mvnw.cmd" if os.name == "nt" and (root / "mvnw.cmd").exists() else ("./mvnw" if (root / "mvnw").exists() else "mvn")
        add("Maven: test", f"{mvn} -q test", "Compiles and runs the Java tests with Maven.", "caution", net)
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        gradle = "gradlew.bat" if os.name == "nt" and (root / "gradlew.bat").exists() else ("./gradlew" if (root / "gradlew").exists() else "gradle")
        add("Gradle: test", f"{gradle} test", "Compiles and runs the tests with Gradle.", "caution", net)
    if (root / "Makefile").exists():
        try:
            targets = re.findall(r"^([A-Za-z0-9_.-]+):", (root / "Makefile").read_text(encoding="utf-8", errors="replace"), re.M)
        except OSError:
            targets = []
        for t in ("test", "check", "lint", "build"):
            if t in targets:
                add(f"make {t}", f"make {t}", f"Runs the '{t}' target from the Makefile.", "caution",
                    ["runs whatever the Makefile defines for this target"], "test" if t in ("test", "check") else t)
    if (root / ".git").exists() and shutil.which("git"):
        add("git status", "git status", "Shows which files changed since the last commit. Changes nothing.", category="info")
        add("git diff (summary)", "git diff --stat", "Summarizes uncommitted changes. Changes nothing.", category="info")
    return presets


# ---------------------------------------------------------------- running
@dataclass
class CommandRun:
    id: str
    command: str
    argv: list[str]
    cwd: str
    level: str
    status: str = "running"  # running | finished | failed | cancelled | timed_out | error
    exit_code: int | None = None
    output: str = ""
    truncated: bool = False
    started: float = field(default_factory=time.time)
    ended: float | None = None
    proc: subprocess.Popen | None = field(default=None, repr=False)

    def to_dict(self, since: int = 0) -> dict:
        return {
            "id": self.id, "command": self.command, "cwd": self.cwd, "level": self.level,
            "status": self.status, "exit_code": self.exit_code, "truncated": self.truncated,
            "output": self.output[since:] if since else self.output, "output_length": len(self.output),
            "started": self.started, "ended": self.ended,
            "seconds": round((self.ended or time.time()) - self.started, 1),
        }


def resolve_executable(argv0: str, ws: Workspace) -> str:
    if Path(argv0).is_absolute():  # an explicit program path, e.g. C:\Python312\python.exe
        if not Path(argv0).is_file():
            raise CommandError(f"'{argv0}' does not exist.")
        return argv0
    if "/" in argv0 or "\\" in argv0:
        path = ws.resolve(argv0)  # relative paths are relative to the project, and must stay inside it
        if os.name == "nt" and not path.exists():
            for ext in (".exe", ".cmd", ".bat"):
                if path.with_name(path.name + ext).exists():
                    return str(path.with_name(path.name + ext))
        if not path.exists():
            raise CommandError(f"'{argv0}' was not found in the project folder.")
        return str(path)
    found = shutil.which(argv0)
    if not found:
        raise CommandError(f"'{argv0}' is not installed or not on your PATH.")
    return found


class CommandRunner:
    def __init__(self, on_finish=None):
        self.runs: dict[str, CommandRun] = {}
        self._lock = threading.Lock()
        self._on_finish = on_finish

    def start(self, command: str, argv: list[str], ws: Workspace, level: str, timeout: int) -> CommandRun:
        exe = resolve_executable(argv[0], ws)
        env = dict(os.environ)
        env.update({"PYTHONUNBUFFERED": "1", "CI": "1", "NO_COLOR": "1", "FORCE_COLOR": "0",
                    "PYTHONIOENCODING": "utf-8"})
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        run = CommandRun(id=uuid.uuid4().hex[:12], command=command, argv=argv, cwd=str(ws.root), level=level)
        try:
            run.proc = subprocess.Popen(
                [exe, *argv[1:]], cwd=ws.root, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, **kwargs)
        except OSError as exc:
            raise CommandError(f"Could not start '{argv[0]}': {exc}") from exc
        with self._lock:
            self.runs[run.id] = run
            # Keep memory bounded: forget the oldest finished runs.
            finished = [r for r in self.runs.values() if r.status != "running"]
            for old in sorted(finished, key=lambda r: r.started)[:-30]:
                self.runs.pop(old.id, None)
        threading.Thread(target=self._pump, args=(run, timeout), daemon=True).start()
        return run

    def _pump(self, run: CommandRun, timeout: int) -> None:
        proc = run.proc
        assert proc and proc.stdout
        timer = threading.Timer(timeout, self._timeout, args=(run,))
        timer.daemon = True
        timer.start()
        try:
            for raw in iter(proc.stdout.readline, b""):
                self._append(run, _ANSI.sub("", raw.decode("utf-8", errors="replace")))
            proc.wait()
        except Exception as exc:  # pragma: no cover - defensive
            self._append(run, f"\n[Jarvis] Error reading output: {exc}\n")
        finally:
            timer.cancel()
        run.exit_code = proc.returncode
        run.ended = time.time()
        if run.status == "running":
            run.status = "finished" if proc.returncode == 0 else "failed"
        if self._on_finish:
            try:
                self._on_finish(run)
            except Exception:
                pass

    def _append(self, run: CommandRun, text: str) -> None:
        run.output += text.replace("\r\n", "\n")
        if len(run.output) > OUTPUT_LIMIT:
            run.output = run.output[-OUTPUT_LIMIT:]
            run.truncated = True

    def _timeout(self, run: CommandRun) -> None:
        if run.status == "running":
            run.status = "timed_out"
            self._append(run, "\n[Jarvis] Stopped: the command ran longer than the time limit.\n")
            _kill_tree(run.proc)

    def cancel(self, run_id: str) -> CommandRun:
        run = self.get(run_id)
        if run.status == "running":
            run.status = "cancelled"
            self._append(run, "\n[Jarvis] Stopped by you.\n")
            _kill_tree(run.proc)
        return run

    def get(self, run_id: str) -> CommandRun:
        run = self.runs.get(run_id)
        if not run:
            raise KeyError(f"No command run with id {run_id}")
        return run

    def cancel_all(self) -> None:
        for run in list(self.runs.values()):
            if run.status == "running":
                self.cancel(run.id)


def _kill_tree(proc: subprocess.Popen | None) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


__all__ = ["CommandError", "CommandRunner", "classify", "detect_presets", "split_command"]
