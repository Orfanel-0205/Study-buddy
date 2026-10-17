"""Keeps secrets out of Jarvis.

Two layers of protection:
1. Files whose *names* suggest secrets (.env, private keys, credential files,
   cloud config folders, ...) are never read, indexed, shown or sent to the model.
2. Text that *is* sent to the model is scanned for common secret formats
   (API keys, tokens, private key blocks, passwords in connection strings)
   and those values are replaced with [REDACTED].

Neither layer is perfect, so the README tells you how to add your own patterns.
"""

from __future__ import annotations

import fnmatch
import re

SENSITIVE_DIRS = {
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".secrets", "secrets",
    ".password-store",
}

SENSITIVE_FILE_PATTERNS = [
    ".env", ".env.*", "*.env", ".envrc", ".flaskenv",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx", "*.ppk",
    "*.gpg", "*.asc", "*.ovpn",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".htpasswd", ".pgpass",
    "credentials", "credentials.*", "secret", "secret.*", "secrets", "secrets.*",
    "token", "token.*", "tokens.*", "*.token", "access_token*", "refresh_token*",
    "service-account*.json", "*serviceaccount*.json", "*-adminsdk-*.json",
    "terraform.tfvars", "*.auto.tfvars", "*.tfstate", "*.tfstate.*",
    "local.settings.json", "wallet.dat",
]

# Substring patterns that would wrongly hide ordinary source code such as
# credential_service.py, so they only apply to config/data files.
BROAD_PATTERNS = ["*credential*", "*secret*", "*api_key*", "*apikey*"]
CODE_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".c",
    ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".dart", ".scala", ".vue",
    ".svelte", ".md", ".rst", ".html", ".css", ".sql",
}

# Templates that document required variables without real values.
SAFE_TEMPLATE_NAMES = {".env.example", ".env.sample", ".env.template", ".env.dist"}

REDACTED = "[REDACTED]"

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
     "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), REDACTED),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), REDACTED),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), REDACTED),
    (re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"), REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), REDACTED),
    (re.compile(r"\b[rs]k_(?:live|test)_[0-9A-Za-z]{16,}\b"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), REDACTED),
]

# password = "hunter2"  /  "apiKey": "abc123"  -> keep the name, hide the value.
_ASSIGNMENT = re.compile(
    r"""(?ix)
    (\b[\w.-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|private[_-]?key|
        auth[_-]?token|access[_-]?token|refresh[_-]?token|client[_-]?secret|bearer)[\w.-]*\b
     ["']?\s*[:=]\s*)
    (["'])([^"'\r\n]{4,})\2
    """
)
# scheme://user:password@host -> scheme://user:[REDACTED]@host
_URL_CREDENTIALS = re.compile(r"\b([a-z][a-z0-9+.\-]*://[^:/\s@]+:)([^@\s/]{2,})(@)", re.I)


def is_sensitive_path(rel_path: str, extra_patterns: list[str] | None = None) -> str | None:
    """Return a reason if the project-relative path looks like it holds secrets."""
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    if not parts:
        return None
    for part in parts[:-1]:
        if part.lower() in SENSITIVE_DIRS:
            return f"inside '{part}', a folder that usually holds credentials"
    name = parts[-1].lower()
    if parts[-1].lower() in SENSITIVE_DIRS:
        return f"'{parts[-1]}' usually holds credentials"
    if name not in SAFE_TEMPLATE_NAMES:
        for pattern in SENSITIVE_FILE_PATTERNS:
            if fnmatch.fnmatchcase(name, pattern):
                return f"name matches the secret-file pattern '{pattern}'"
        ext = ("." + name.rsplit(".", 1)[-1]) if "." in name else ""
        if ext not in CODE_EXTENSIONS:
            for pattern in BROAD_PATTERNS:
                if fnmatch.fnmatchcase(name, pattern):
                    return f"name matches the secret-file pattern '{pattern}'"
    rel_norm = "/".join(parts)
    for pattern in extra_patterns or []:
        p = pattern.replace("\\", "/").strip("/")
        if fnmatch.fnmatch(rel_norm, p) or fnmatch.fnmatch(parts[-1], p) or any(
            fnmatch.fnmatch(part, p) for part in parts[:-1]
        ):
            return f"matches your exclude pattern '{pattern}'"
    return None


def redact(text: str) -> tuple[str, int]:
    """Replace likely secret values. Returns (redacted_text, number_of_replacements)."""
    count = 0
    for pattern, replacement in _SECRET_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n

    hidden = 0

    def _assign(m: re.Match) -> str:
        nonlocal hidden
        value = m.group(3)
        if value.startswith("[REDACTED") or value.startswith(("${", "{{", "%(", "<")):
            return m.group(0)  # already hidden, or a template placeholder
        hidden += 1
        return f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(2)}"

    text = _ASSIGNMENT.sub(_assign, text)
    count += hidden
    text, n = _URL_CREDENTIALS.subn(lambda m: f"{m.group(1)}{REDACTED}{m.group(3)}", text)
    count += n
    return text, count
