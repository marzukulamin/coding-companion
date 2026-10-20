from __future__ import annotations

import os
import sys
import tomllib
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .common import CompanionError, digest, read_bounded


@dataclass(frozen=True)
class Config:
    max_files: int = 20000
    max_file_bytes: int = 5 * 1024 * 1024
    max_inventory_bytes: int = 64 * 1024 * 1024
    max_output_bytes: int = 2 * 1024 * 1024
    max_state_bytes: int = 256 * 1024 * 1024
    timeout_seconds: int = 60
    debounce_seconds: float = 0.75
    poll_seconds: float = 2.0
    max_mailbox_files: int = 100
    request_timeout_seconds: int = 65
    memory_enabled: bool = True
    max_process_memory_bytes: int = 512 * 1024 * 1024
    max_fast_workers: int = 2
    max_expensive_workers: int = 1
    max_pending_jobs: int = 100
    aging_seconds: float = 5.0
    artifact_retention_days: int = 7
    event_retention_days: int = 7

    @property
    def fingerprint(self) -> str:
        return digest(asdict(self))


def load_config(path: Path | None = None) -> Config:
    if path is None:
        return Config()
    try:
        data = tomllib.loads(read_bounded(path, 65536).decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise CompanionError("Invalid companion configuration") from exc
    # Repository configuration never supplies permissions, commands or data-use policy.
    allowed = set(Config.__dataclass_fields__)
    if set(data) - {"resources"} or not isinstance(data.get("resources", {}), dict):
        raise CompanionError("Only a [resources] table is accepted by runtime config v1")
    values = data.get("resources", {})
    if set(values) - allowed:
        raise CompanionError("Unknown resource setting")
    for key, value in values.items():
        default = getattr(Config(), key)
        if isinstance(default, bool):
            valid = type(value) is bool
        else:
            valid = type(value) in (int, float) and value > 0 and math.isfinite(value)
            if isinstance(default, int):
                valid = type(value) is int and value > 0
        if not valid:
            raise CompanionError(f"Invalid resource setting: {key}")
    result = Config(**values)
    if result.max_output_bytes > 10 * 1024 * 1024 or result.max_files > 100000 or result.timeout_seconds > 600:
        raise CompanionError("Resource setting exceeds supported upper bound")
    if result.max_fast_workers > 8 or result.max_expensive_workers > 4 or result.max_pending_jobs > 1000:
        raise CompanionError("Worker/queue setting exceeds supported upper bound")
    return result


def project_id(root: Path) -> str:
    return digest(str(root.resolve()))[:32]


def state_root(root: Path, override: Path | None = None) -> Path:
    if override is not None:
        base = override.resolve()
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "CodingCompanion/projects"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/CodingCompanion/projects"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "coding-companion/projects"
    return base / project_id(root)
