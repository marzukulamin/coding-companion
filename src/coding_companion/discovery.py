from __future__ import annotations

import json
import os
import platform
import sys
import tomllib
import ast
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .common import CompanionError, digest, read_bounded
from .config import Config

EXCLUDED = {".git", ".codex", ".agents", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".companion", "runtime-state", ".architecture-validation", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", "target"}
LANGUAGES = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript", ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp", ".rb": "ruby", ".php": "php", ".sql": "sql"}
MANIFESTS = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml", "requirements.txt", "Gemfile", "composer.json", "Makefile", "Dockerfile", "compose.yml", "docker-compose.yml"}


def environment_hash():
    return digest({"python": sys.version, "os": platform.system(), "machine": platform.machine()})


@dataclass
class Snapshot:
    snapshot_id: str
    files: dict[str, dict]
    contents: dict[str, bytes]
    gaps: list[str]
    environment_hash: str
    policy_hash: str
    provenance: dict = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.gaps


def snapshot(root: Path, config: Config, state: Path | None = None, cache=None) -> Snapshot:
    files, contents, gaps = {}, {}, []
    root = root.resolve()
    if not root.is_dir():
        raise CompanionError("Project root must be a directory")
    count, total_bytes = 0, 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        safe_dirs = []
        for name in sorted(dirs):
            path = parent / name
            if name in EXCLUDED or (state and (path.resolve() == state.resolve() or state.resolve().is_relative_to(path.resolve()))):
                continue
            if path.is_symlink() or path.is_junction():
                gaps.append(f"Linked directory excluded: {path.relative_to(root).as_posix()}")
            else:
                safe_dirs.append(name)
        dirs[:] = safe_dirs
        for name in sorted(names):
            path = parent / name
            rel = path.relative_to(root).as_posix()
            if name.startswith(".env") or path.suffix in {".pyc", ".db", ".sqlite", ".png", ".jpg", ".mp4", ".zip", ".pdf", ".exe", ".dll"}:
                continue
            count += 1
            if count > config.max_files:
                gaps.append("File inventory limit reached")
                dirs[:] = []
                break
            try:
                stat = path.stat(follow_symlinks=False)
                signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                cached = cache.entries.get(rel) if cache is not None else None
                data = cached[1] if cached and cached[0] == signature and not path.is_symlink() and not path.is_junction() else read_bounded(path, config.max_file_bytes)
                if cache is not None:
                    cache.entries[rel] = (signature, data)
                total_bytes += len(data)
                if total_bytes > config.max_inventory_bytes:
                    gaps.append("Inventory byte budget reached")
                    env = environment_hash()
                    return Snapshot(digest({"files": files, "environment": env, "policy": config.fingerprint, "gaps": gaps}), files, contents, gaps, env, config.fingerprint)
                contents[rel] = data
                files[rel] = {"hash": digest(data), "size": len(data)}
            except (OSError, CompanionError) as exc:
                gaps.append(f"Unavailable input: {rel} ({type(exc).__name__})")
        if count > config.max_files:
            break
    env = environment_hash()
    identity = digest({"files": files, "environment": env, "policy": config.fingerprint, "gaps": gaps})
    return Snapshot(identity, files, contents, gaps, env, config.fingerprint)


class InventoryCache:
    """Poll optimization only. Execution/verification always performs fresh hashes."""
    def __init__(self, reconcile_seconds=60):
        self.entries, self.last_reconcile = {}, 0.0
        self.reconcile_seconds = reconcile_seconds

    def read(self, root, config, state):
        clock = time.monotonic()
        if clock - self.last_reconcile >= self.reconcile_seconds:
            self.entries.clear()
            self.last_reconcile = clock
        result = snapshot(root, config, state, self)
        self.entries = {p: entry for p, entry in self.entries.items() if p in result.files}
        return result


def discover(root: Path, config: Config, state: Path | None = None) -> dict:
    snap = snapshot(root, config, state)
    languages = sorted({LANGUAGES[Path(p).suffix] for p in snap.files if Path(p).suffix in LANGUAGES})
    packages, commands, dependencies = [], [], set()
    for path in snap.files:
        name = Path(path).name
        if name not in MANIFESTS and not name.endswith(".csproj"):
            continue
        item = {"path": path, "kind": name, "parsed": False}
        try:
            raw = snap.contents[path].decode("utf-8-sig")
            if name == "package.json":
                manifest = json.loads(raw)
                if not isinstance(manifest, dict) or any(not isinstance(manifest.get(key, {}), dict) for key in ("dependencies", "devDependencies", "scripts")) or any(not isinstance(script, str) for script in manifest.get("scripts", {}).values()):
                    raise ValueError("Invalid package manifest shape")
                item.update(name=manifest.get("name"), parsed=True, dependencies=sorted(set(manifest.get("dependencies", {})) | set(manifest.get("devDependencies", {}))))
                dependencies.update(item["dependencies"])
                for key, script in manifest.get("scripts", {}).items():
                    commands.append({"package": str(Path(path).parent), "name": key, "command": script, "trust": "unreviewed", "source_hash": snap.files[path]["hash"]})
            elif name in {"pyproject.toml", "Cargo.toml"}:
                manifest = tomllib.loads(raw)
                item.update(parsed=True, name=manifest.get("project", manifest.get("package", {})).get("name"))
                if name == "pyproject.toml":
                    dependencies.update(re.split(r"[<>=!\[;\s]", dep, maxsplit=1)[0].lower() for dep in manifest.get("project", {}).get("dependencies", []) if isinstance(dep, str))
                    dependencies.update(manifest.get("tool", {}).keys())
                    for group in manifest.get("project", {}).get("optional-dependencies", {}).values():
                        dependencies.update(re.split(r"[<>=!\[;\s]", dep, maxsplit=1)[0].lower() for dep in group if isinstance(dep, str))
                else:
                    dependencies.update(manifest.get("dependencies", {}).keys())
            else:
                item["parsed"] = True
        except (ValueError, UnicodeError, AttributeError, TypeError):
            item["error"] = "Invalid manifest; run structured.formats"
        packages.append(item)
    git_root = next((str(p) for p in [root, *root.parents] if (p / ".git").exists()), None)
    frameworks = sorted(dependencies.intersection({"react", "next", "vue", "angular", "svelte", "express", "fastapi", "django", "flask", "pytest", "playwright", "vitest", "jest", "typescript", "eslint", "vite", "torch", "transformers", "langchain"}))
    services = [{"name": name, "basis": "dependency_manifest", "confidence": "medium"} for name, tools in {"postgresql": {"pg", "psycopg", "psycopg2", "asyncpg"}, "redis": {"redis", "ioredis"}, "mysql": {"mysql", "mysql2", "pymysql"}, "object_storage": {"boto3", "@aws-sdk/client-s3"}, "model_endpoint": {"openai", "anthropic", "transformers"}}.items() if dependencies.intersection(tools)]
    declared_environment = set()
    for data in snap.contents.values():
        text = data.decode("utf-8", errors="replace")
        declared_environment.update(re.findall(r"(?:process\.env\.|os\.environ\[['\"])([A-Z][A-Z0-9_]*)", text))
    requirement_path = "companion.requirements.json"
    requirements = {}
    if requirement_path in snap.contents:
        try:
            supplied = json.loads(snap.contents[requirement_path])
            allowed = {"acceptance_criteria", "journeys", "invariants", "roles", "environments", "traffic", "browsers", "model", "data"}
            if not isinstance(supplied, dict) or set(supplied) - allowed:
                raise ValueError()
            requirements = supplied
        except (ValueError, UnicodeError):
            snap.gaps.append("Invalid companion.requirements.json")
    unknowns = [key for key in ("acceptance_criteria", "environments", "traffic", "browsers", "model", "data") if key not in requirements]
    result = {"project_root": str(root), "repository_root": git_root, "worktree_root": str(root), "languages": languages, "frameworks": frameworks, "packages": packages, "commands": commands, "services": services, "environment_names": sorted(declared_environment), "requirements": requirements, "requirements_trust": "Repository-supplied diagnostic context, never permission policy", "snapshot_id": snap.snapshot_id, "file_count": len(snap.files), "coverage": "complete" if snap.complete else "partial", "gaps": snap.gaps, "unknowns": unknowns, "visibility_limits": ["Saved files only", "No external environment or unsaved editor access", "Services are not started or contacted"]}
    from .impact import impact_graph
    from .adapters import proposals
    result["impact_graph"] = impact_graph(snap)
    result["native_proposals"] = proposals(result, snap)
    return result
