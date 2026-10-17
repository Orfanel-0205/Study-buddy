"""Builds the project context sent to the model along with your question.

Only files inside the open project are used, secret-looking files are never
included, and secret-looking values are redacted. Every file that contributes
is returned as a 'source' so the interface can show what informed the answer.
"""

from __future__ import annotations

from pathlib import Path

from ..project.index import ProjectIndex
from ..project.secrets import redact
from ..project.workspace import LANGUAGES, Workspace

FENCE_LANG = {
    "Python": "python", "JavaScript": "javascript", "TypeScript": "typescript", "Java": "java",
    "Go": "go", "Rust": "rust", "C#": "csharp", "C++": "cpp", "C": "c", "Ruby": "ruby",
    "PHP": "php", "Shell": "bash", "PowerShell": "powershell", "HTML": "html", "CSS": "css",
    "SQL": "sql", "JSON": "json", "YAML": "yaml", "Markdown": "markdown", "TOML": "toml",
}


def _lang(path: str) -> str:
    lang = LANGUAGES.get(Path(path).suffix.lower(), "")
    return FENCE_LANG.get(lang.split(" (")[0], "")


def build_project_context(ws: Workspace, index: ProjectIndex | None, query: str,
                          attached: list[str], budget: int, use_search: bool = True,
                          overview: dict | None = None) -> tuple[str, list[dict], int]:
    """Return (context_markdown, sources, number_of_redactions)."""
    parts: list[str] = []
    sources: list[dict] = []
    redactions = 0
    used = 0

    if overview:
        langs = ", ".join(f"{name} ({n})" for name, n in overview.get("languages", [])) or "unknown"
        block = (f"## Project: {overview['name']}\n"
                 f"Languages (file counts): {langs}\n"
                 f"Key files: {', '.join(overview.get('key_files', [])) or 'none found'}\n"
                 f"Top-level items: {', '.join(overview.get('top_level', [])[:30])}\n")
        parts.append(block)
        used += len(block)

    # 1) Files the user attached explicitly get up to ~70% of the budget.
    attached_budget = int(budget * (0.7 if use_search else 1.0))
    seen: set[str] = set()
    for rel in attached:
        if rel in seen:
            continue
        seen.add(rel)
        try:
            text = ws.read_text(rel)
        except (OSError, PermissionError) as exc:
            parts.append(f"### {rel}\n(Could not include this file: {exc})\n")
            continue
        text, n = redact(text)
        redactions += n
        lines = text.splitlines()
        room = max(attached_budget - used, 0)
        truncated = False
        if len(text) > room:
            keep, size = [], 0
            for line in lines:
                if size + len(line) + 1 > room:
                    break
                keep.append(line)
                size += len(line) + 1
            lines, truncated = keep, True
        if truncated and not lines:
            parts.append(f"### {rel}\n(Skipped: no room left in the context budget.)\n")
            continue
        end = len(lines)
        # No per-line numbers: small models copy them into the code they write.
        body = "\n".join(lines)
        note = f" (showing lines 1-{end}; the rest was cut to fit)" if truncated else f" (all {end} lines)"
        parts.append(f"### File attached by the user: {rel}{note}\n```{_lang(rel)}\n{body}\n```\n")
        used += len(body) + 80
        sources.append({"path": rel, "start_line": 1, "end_line": end, "kind": "attached"})

    # 2) Keyword search results fill what's left.
    if use_search and index is not None and query.strip():
        hits = [h for h in index.search(query, k=8) if h["path"] not in seen]
        added_header = False
        for hit in hits:
            text, n = redact(hit["text"])
            body = text
            if used + len(body) + 100 > budget:
                continue
            if not added_header:
                parts.append("## Excerpts found by keyword search (may be incomplete; ask for a file if you need more)\n")
                added_header = True
            redactions += n
            parts.append(f"### {hit['path']} lines {hit['start_line']}-{hit['end_line']}\n```{_lang(hit['path'])}\n{body}\n```\n")
            used += len(body) + 100
            sources.append({"path": hit["path"], "start_line": hit["start_line"],
                            "end_line": hit["end_line"], "kind": "search"})

    parts.append("(Files that may hold secrets, such as .env files and private keys, are never shared; "
                 "secret-looking values are replaced with [REDACTED].)")
    return "\n".join(parts), sources, redactions
