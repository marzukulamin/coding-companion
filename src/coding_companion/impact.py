from __future__ import annotations

import ast
import re
import json
from pathlib import PurePosixPath

GLOBAL_INPUTS = {"pyproject.toml", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "schema.sql", "companion.requirements.json", "companion.data.json", "companion.rag.json", "companion.evals.json", "companion.model.json", "companion.training.json", "companion.metrics.json"}
JS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")


def javascript_dependencies(path, data, files, resolver=None):
    """Conservative lexical import handling; ambiguous/runtime relationships force full scope."""
    text = data.decode("utf-8", errors="replace")
    references = []
    # Include side-effect imports, re-exports, import type and CommonJS references.
    static = r"\b(?:from\s*|import\s*)(['\"])([^'\"\r\n]+)\1"
    calls = r"\b(?:import|require)\s*\(\s*(['\"])([^'\"\r\n]+)\1\s*\)"
    references.extend(match.group(2) for match in re.finditer(static, text))
    literal_calls = list(re.finditer(calls, text))
    references.extend(match.group(2) for match in literal_calls)
    unknown = bool(re.search(r"\b(?:import|require)\s*\(", re.sub(calls, "", text)) or re.search(r"\bimport\s*\.\s*meta\s*\.\s*glob|\brequire\s*\.\s*resolve", text))
    dependencies = set()
    for target in references:
        target = re.split(r"[?#]", target, maxsplit=1)[0]
        from .js_resolution import local_join
        if target.startswith("."):
            resolved = local_join(str(PurePosixPath(path).parent), target)
            prefixes = [resolved] if resolved is not None else None
        else:
            prefixes = resolver.targets(path, target) if resolver else None
        if not prefixes:
            unknown = True
            continue
        matched = False
        for prefix in prefixes:
            candidates = [prefix, *[prefix + ext for ext in JS_SUFFIXES], *[prefix + "/index" + ext for ext in JS_SUFFIXES]]
            # TS projects commonly import emitted .js names from .ts sources.
            substitutions = {".js": (".ts", ".tsx", ".d.ts"), ".jsx": (".tsx", ".ts"), ".mjs": (".mts", ".d.mts"), ".cjs": (".cts", ".d.cts")}
            suffix = PurePosixPath(prefix).suffix
            candidates += [prefix[:-len(suffix)] + ext for ext in substitutions.get(suffix, ())]
            found = set(candidates).intersection(files)
            if found:
                dependencies.update(found)
                matched = True
        if not matched:
            unknown = True
    return dependencies, unknown


def broad_input(path):
    name = PurePosixPath(path).name
    return name in GLOBAL_INPUTS or "/migrations/" in "/" + path or name.startswith(("tsconfig", "jsconfig")) or ".config." in name or name in {"conftest.py", "setup.py", "setup.cfg", "pytest.ini", ".npmrc", ".yarnrc.yml"}


def impact_graph(snap) -> dict:
    from .js_resolution import LocalResolver
    resolver = LocalResolver(snap)
    edges, unresolved = {}, []
    modules = {}
    for path in snap.files:
        if path.endswith(".py"):
            module = path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
            modules[module] = path
            if module.startswith("src."):
                modules[module[4:]] = path
    for path, data in snap.contents.items():
        dependencies = set()
        if path.endswith(".py"):
            try:
                tree = ast.parse(data)
                dynamic_names = {"__import__", "import_module", "exec", "eval"}
                dynamic_names.update(alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "importlib" for alias in node.names if alias.name == "import_module")
                if any(isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id in dynamic_names) or (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")) for node in ast.walk(tree)):
                    unresolved.append(path)
                for node in ast.walk(tree):
                    names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                    for name in names:
                        candidates = [name]
                        if isinstance(node, ast.ImportFrom) and node.level:
                            base = list(PurePosixPath(path).parent.parts)
                            base = base[:len(base) - node.level + 1]
                            candidates = [".".join([*base, name]).strip(".")]
                            candidates += [".".join([*base, name, alias.name]).strip(".") for alias in node.names]
                        elif isinstance(node, ast.ImportFrom):
                            candidates += [".".join([name, alias.name]).strip(".") for alias in node.names]
                        for candidate in candidates:
                            if candidate in modules:
                                dependencies.add(modules[candidate])
                            # Importing a submodule also executes its package initializers.
                            for end in range(1, len(candidate.split("."))):
                                ancestor = ".".join(candidate.split(".")[:end])
                                if ancestor in modules and modules[ancestor].endswith("/__init__.py"):
                                    dependencies.add(modules[ancestor])
            except (SyntaxError, ValueError, RecursionError):
                unresolved.append(path)
        elif path.endswith(JS_SUFFIXES):
            dependencies, unknown = javascript_dependencies(path, data, snap.files, resolver)
            if unknown:
                unresolved.append(path)
        elif PurePosixPath(path).name.startswith("companion.") and path.endswith(".json"):
            try:
                document = json.loads(data)
                def references(value):
                    if isinstance(value, dict):
                        for key, child in value.items():
                            if key == "path" and isinstance(child, str) and child in snap.files:
                                dependencies.add(child)
                            references(child)
                    elif isinstance(value, list):
                        for child in value:
                            references(child)
                references(document)
            except (ValueError, UnicodeError, RecursionError):
                unresolved.append(path)
        if dependencies:
            edges[path] = sorted(dependencies)
    return {"edges": edges, "unresolved": sorted(set(unresolved)), "supported_relationships": ["Python local imports and package initializers", "JavaScript/TypeScript relative imports, side effects and re-exports", "Local tsconfig/jsconfig paths and unconditional local package exports", "Explicit contract path references"], "unknown_relationships": ["Computed imports, bundler aliases, conditional exports and external packages", "External service/data dependencies", "Generated/runtime routing", "Lexical JavaScript analysis is not a complete parser"]}


def affected(snap, changed: list[str]) -> dict:
    graph = impact_graph(snap)
    broad = any(broad_input(p) for p in changed)
    referenced = {p for dependencies in graph["edges"].values() for p in dependencies}
    unsupported = any(PurePosixPath(p).suffix not in {".py", *JS_SUFFIXES} and p not in referenced for p in changed)
    if not changed or broad or unsupported or graph["unresolved"] or any(p not in snap.files for p in changed):
        return {"paths": sorted(snap.files), "scope": "project", "reason": "Broad-impact, deleted, or unresolved dependency input", "changed": changed}
    result = set(changed)
    while True:
        extra = {consumer for consumer, deps in graph["edges"].items() if result.intersection(deps)}
        if extra <= result:
            break
        result.update(extra)
    return {"paths": sorted(result), "scope": "changed", "reason": "Static local import closure; unknown external relationships remain coverage gaps", "changed": changed}
