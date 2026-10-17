"""Sandboxed access to the project folder you selected.

Every path is resolved (following symlinks) and checked to be inside the
project root before anything is read or written, so "../../" tricks and links
pointing elsewhere are refused. Secret-looking files are refused too.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from .secrets import is_sensitive_path

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".nox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".next", ".nuxt",
    ".svelte-kit", "target", "obj", ".gradle", ".idea", "coverage", "htmlcov", ".cache",
    ".parcel-cache", ".turbo", "vendor", "bower_components", ".terraform", "Pods",
    "DerivedData", ".dart_tool", ".expo", "site-packages", "egg-info",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".psd", ".svgz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".war", ".whl",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".lib", ".obj", ".class", ".pyc",
    ".pyd", ".wasm", ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg",
    ".ttf", ".otf", ".woff", ".woff2", ".eot", ".db", ".sqlite", ".sqlite3", ".gguf",
    ".onnx", ".pt", ".pth", ".h5", ".pkl", ".npy", ".npz", ".parquet", ".lock.db",
}

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript (React)", ".ts": "TypeScript", ".tsx": "TypeScript (React)",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".go": "Go",
    ".rs": "Rust", ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++",
    ".hpp": "C++", ".cs": "C#", ".fs": "F#", ".vb": "Visual Basic", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".m": "Objective-C", ".dart": "Dart", ".lua": "Lua",
    ".r": "R", ".jl": "Julia", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".hs": "Haskell", ".clj": "Clojure", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
    ".ps1": "PowerShell", ".bat": "Batch", ".cmd": "Batch", ".html": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".less": "Less", ".vue": "Vue", ".svelte": "Svelte", ".md": "Markdown",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".xml": "XML",
    ".tf": "Terraform", ".proto": "Protocol Buffers", ".graphql": "GraphQL", ".ipynb": "Jupyter",
}

KEY_FILES = [
    "README.md", "README.rst", "README.txt", "package.json", "pyproject.toml", "setup.py",
    "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json", "Makefile",
    "CMakeLists.txt", "Dockerfile", "docker-compose.yml", "compose.yaml", "tsconfig.json",
    "vite.config.ts", "vite.config.js", "next.config.js", "angular.json", "pubspec.yaml",
    "mix.exs", ".github/workflows", "pytest.ini", "tox.ini", "jest.config.js",
]


class AccessDenied(PermissionError):
    pass


class Workspace:
    def __init__(self, root: str | os.PathLike, extra_exclude: list[str] | None = None,
                 max_file_bytes: int = 300_000):
        path = Path(root).expanduser()
        if not path.is_absolute():
            raise AccessDenied("Please give the full path of the project folder.")
        if not path.exists():
            raise FileNotFoundError(f"The folder '{path}' does not exist.")
        if not path.is_dir():
            raise NotADirectoryError(f"'{path}' is a file, not a folder.")
        path = path.resolve()
        if path.parent == path:
            raise AccessDenied("Pick a specific project folder, not the root of a drive.")
        if path == Path.home().resolve():
            raise AccessDenied("Pick a specific project folder, not your whole home folder.")
        self.root = path
        self.name = path.name
        self.extra_exclude = list(extra_exclude or [])
        self.max_file_bytes = max_file_bytes

    # ---- path safety -------------------------------------------------
    def resolve(self, rel: str) -> Path:
        rel = (rel or "").strip().replace("\\", "/")
        candidate = Path(rel)
        if candidate.is_absolute() or candidate.drive:
            target = candidate.resolve()
        else:
            target = (self.root / rel).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise AccessDenied(f"'{rel}' is outside the project folder, so Jarvis won't touch it.")
        return target

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() if path != self.root else ""

    def sensitive_reason(self, rel: str) -> str | None:
        return is_sensitive_path(rel, self.extra_exclude)

    def check_readable(self, rel: str) -> Path:
        path = self.resolve(rel)
        reason = self.sensitive_reason(self.rel(path))
        if reason:
            raise AccessDenied(f"'{self.rel(path)}' is hidden because it may contain secrets ({reason}).")
        return path

    def check_writable(self, rel: str) -> Path:
        path = self.check_readable(rel)
        if path == self.root:
            raise AccessDenied("That is the project folder itself, not a file.")
        parts = Path(self.rel(path)).parts
        if parts and parts[0] in (".git", ".hg", ".svn"):
            raise AccessDenied("Jarvis does not edit version-control internals (.git).")
        return path

    # ---- reading -----------------------------------------------------
    def list_dir(self, rel: str = "") -> list[dict]:
        folder = self.check_readable(rel)
        if not folder.is_dir():
            raise NotADirectoryError(f"'{rel}' is not a folder.")
        entries = []
        try:
            children = list(folder.iterdir())
        except PermissionError as exc:
            raise AccessDenied(f"The operating system denied access to '{rel}'.") from exc
        for child in children:
            try:
                resolved = child.resolve()
                if not resolved.is_relative_to(self.root):
                    continue  # symlink pointing outside the project: hide it
                is_dir = child.is_dir()
                child_rel = self.rel(child)
                entries.append({
                    "name": child.name,
                    "path": child_rel,
                    "type": "dir" if is_dir else "file",
                    "size": 0 if is_dir else child.stat().st_size,
                    "sensitive": bool(self.sensitive_reason(child_rel)),
                    "ignored": is_dir and child.name in IGNORED_DIRS,
                })
            except OSError:
                continue
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
        return entries

    def is_binary(self, path: Path) -> bool:
        if path.suffix.lower() in BINARY_EXTENSIONS:
            return True
        try:
            with path.open("rb") as fh:
                return b"\x00" in fh.read(8192)
        except OSError:
            return True

    def read_text(self, rel: str) -> str:
        path = self.check_readable(rel)
        if not path.is_file():
            raise FileNotFoundError(f"'{rel}' is not a file in the project.")
        size = path.stat().st_size
        if size > self.max_file_bytes:
            raise AccessDenied(
                f"'{rel}' is {size // 1024} KB, larger than the {self.max_file_bytes // 1024} KB "
                "limit (change 'Max file size' in Settings).")
        if self.is_binary(path):
            raise AccessDenied(f"'{rel}' is a binary file, so it can't be shown as text.")
        data = path.read_bytes()
        return data.decode("utf-8-sig", errors="replace")

    def iter_files(self, max_files: int | None = None):
        """Yield project-relative paths of readable text files, skipping noise and secrets."""
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            base = Path(dirpath)
            rel_base = self.rel(base)
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in IGNORED_DIRS and not d.endswith(".egg-info")
                and not self.sensitive_reason(f"{rel_base}/{d}".lstrip("/") + "/x")
            )
            for name in sorted(filenames):
                rel = f"{rel_base}/{name}".lstrip("/")
                path = base / name
                if self.sensitive_reason(rel) or path.suffix.lower() in BINARY_EXTENSIONS:
                    continue
                try:
                    if path.is_symlink() and not path.resolve().is_relative_to(self.root):
                        continue
                    if path.stat().st_size > self.max_file_bytes:
                        continue
                except OSError:
                    continue
                yield rel
                count += 1
                if max_files and count >= max_files:
                    return

    def overview(self, max_files: int = 4000) -> dict:
        langs: Counter = Counter()
        total = 0
        for rel in self.iter_files(max_files):
            total += 1
            lang = LANGUAGES.get(Path(rel).suffix.lower())
            if lang:
                langs[lang] += 1
        key_files = [k for k in KEY_FILES if (self.root / k).exists()]
        key_files += sorted(p.name for p in self.root.glob("*.sln"))[:3]
        key_files += sorted(p.name for p in self.root.glob("*.csproj"))[:3]
        top = []
        for e in self.list_dir("")[:40]:
            top.append(e["name"] + ("/" if e["type"] == "dir" else "") + (" (hidden: secrets)" if e["sensitive"] else ""))
        return {
            "name": self.name,
            "root": str(self.root),
            "file_count": total,
            "languages": langs.most_common(8),
            "key_files": key_files,
            "top_level": top,
            "is_git": (self.root / ".git").exists(),
        }
