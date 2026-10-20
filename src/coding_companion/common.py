from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


class CompanionError(Exception):
    """An explicit incomplete operation, never a successful check."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def identifier() -> str:
    return str(uuid.uuid4())


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def strict_json(value):
    def invalid(constant):
        raise ValueError("Nonfinite JSON constants are not valid evidence")
    return json.loads(value, parse_constant=invalid)


def digest(value) -> str:
    data = value if isinstance(value, bytes) else canonical(value).encode()
    return hashlib.sha256(data).hexdigest()


def inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise CompanionError("Path escapes registered root")
    return resolved


def read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or path.is_junction():
        raise CompanionError("Linked inputs are not followed")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise CompanionError("Input exceeds byte limit")
    return data


def file_digest(path: Path, limit: int) -> str:
    if path.is_symlink() or path.is_junction():
        raise CompanionError("Linked file hash rejected")
    hashed, total = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while data := handle.read(1024 * 1024):
            total += len(data)
            if total > limit:
                raise CompanionError("File hash byte bound exceeded")
            hashed.update(data)
    return hashed.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.is_junction():
        raise CompanionError("Refusing linked output")
    fd, temp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def redact(text: str) -> str:
    """Redact complete bounded evidence before writing it, never chunk by chunk."""
    text = re.sub(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[REDACTED KEY]", text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|AKIA[A-Z0-9]{16})\b", "[REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED JWT]", text)
    text = re.sub(r"(?im)(authorization\s*:\s*)(?:Bearer|Basic)\s+[^\r\n,;]+", r"\1[REDACTED]", text)
    text = re.sub(r'''(?is)(\b(?:password|passwd|secret|api[_-]?key|token|authorization)\b["']?\s*[=:]\s*)(["'])(.*?)\2''', r"\1\2[REDACTED]\2", text)
    text = re.sub(r'''(?i)(\b(?:password|passwd|secret|api[_-]?key|token|authorization)\b\s*[=:]\s*)([^\s,"';]+)''', r"\1[REDACTED]", text)
    return re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", text)
