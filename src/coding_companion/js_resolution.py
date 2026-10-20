"""Bounded local TypeScript aliases and workspace exports for impact routing.

Unsupported configuration always remains unresolved. This resolves possible local
inputs, not the complete runtime semantics of a JavaScript module loader.
"""
from __future__ import annotations

import json
import posixpath
from pathlib import PurePosixPath


def local_join(base, target):
    if not isinstance(target, str) or "\\" in target or ":" in target or target.startswith("/"):
        return None
    result = posixpath.normpath(posixpath.join(base, target))
    return None if result == ".." or result.startswith("../") else result.removeprefix("./")


def json_config(data):
    """Strip JSONC comments/trailing commas without altering string contents."""
    text = data.decode("utf-8-sig")
    output, index, quoted, escape = [], 0, False, False
    while index < len(text):
        char = text[index]
        if quoted:
            output.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            output.append(char)
        elif text[index:index + 2] == "//":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        elif text[index:index + 2] == "/*":
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated configuration comment")
            output.append(" ")
            index = end + 2
            continue
        else:
            output.append(char)
        index += 1
    text = "".join(output)
    output, quoted, escape = [], False, False
    for index, char in enumerate(text):
        if not quoted and char == "," and text[index + 1:].lstrip().startswith(("}", "]")):
            continue
        output.append(char)
        if escape:
            escape = False
        elif quoted and char == "\\":
            escape = True
        elif char == '"':
            quoted = not quoted
    result = json.loads("".join(output))
    if not isinstance(result, dict):
        raise ValueError("Configuration must be an object")
    return result


class LocalResolver:
    def __init__(self, snap):
        self.contents = snap.contents
        self.packages = {}
        self.cache = {}
        for path, data in snap.contents.items():
            if PurePosixPath(path).name == "package.json":
                try:
                    package = json.loads(data)
                    if isinstance(package, dict) and isinstance(package.get("name"), str):
                        self.packages.setdefault(package["name"], []).append((str(PurePosixPath(path).parent), package))
                except (ValueError, UnicodeError, RecursionError):
                    pass

    def configuration(self, path, trail=()):
        if path in trail or len(trail) >= 16:
            raise ValueError("Cyclic or excessive configuration inheritance")
        if path in self.cache:
            return self.cache[path]
        config = json_config(self.contents[path])
        base, aliases = None, {}
        if "extends" in config:
            target = config["extends"]
            if not isinstance(target, str) or not target.startswith("."):
                raise ValueError("Only local single configuration inheritance is supported")
            parent = local_join(str(PurePosixPath(path).parent), target)
            if parent not in self.contents:
                parent = (parent + ".json") if parent else None
            if parent not in self.contents:
                raise ValueError("Configuration parent is unavailable")
            base, aliases = self.configuration(parent, (*trail, path))
            aliases = dict(aliases)
        options = config.get("compilerOptions", {})
        if not isinstance(options, dict):
            raise ValueError("Invalid compiler options")
        # Inherited path mappings retain their declaring config's resolution base.
        declared_base = local_join(str(PurePosixPath(path).parent), options.get("baseUrl", "."))
        if declared_base is None:
            raise ValueError("Base URL escapes bounded project")
        if "baseUrl" in options:
            if aliases and "paths" not in options and base != declared_base:
                raise ValueError("Overriding inherited alias base requires explicit path mappings")
            base = declared_base
        if "paths" in options:
            paths = options["paths"]
            if not isinstance(paths, dict) or len(paths) > 100:
                raise ValueError("Invalid or excessive path mappings")
            aliases = {}
            for key, values in paths.items():
                if not isinstance(key, str) or key.count("*") > 1 or not isinstance(values, list) or not 1 <= len(values) <= 20:
                    raise ValueError("Invalid alias pattern")
                candidates = [local_join(base or declared_base, value) for value in values]
                if any(value is None or value.count("*") > 1 for value in candidates):
                    raise ValueError("Alias target escapes project")
                aliases[key] = candidates
        result = base, aliases
        self.cache[path] = result
        return result

    def nearest_config(self, path):
        parent = PurePosixPath(path).parent
        for directory in (parent, *parent.parents):
            for name in ("tsconfig.json", "jsconfig.json"):
                candidate = (directory / name).as_posix()
                if candidate in self.contents:
                    return candidate
        return None

    @staticmethod
    def match(pattern, target):
        if "*" not in pattern:
            return "" if pattern == target else None
        prefix, suffix = pattern.split("*")
        if target.startswith(prefix) and target.endswith(suffix) and len(target) >= len(prefix) + len(suffix):
            return target[len(prefix):len(target) - len(suffix) if suffix else None]
        return None

    def targets(self, path, target):
        """Return possible local prefixes, or None for unknown resolution."""
        config = self.nearest_config(path)
        if config:
            try:
                base, aliases = self.configuration(config)
                matches = [(key, self.match(key, target)) for key in aliases]
                matches = [(key, value) for key, value in matches if value is not None]
                if matches:
                    # Exact mappings win; otherwise longest prefix/suffix wins.
                    key, value = max(matches, key=lambda pair: ("*" not in pair[0], len(pair[0].split("*")[0]), len(pair[0])))
                    return [candidate.replace("*", value) for candidate in aliases[key]]
            except (ValueError, KeyError, UnicodeError, RecursionError):
                return None
        names = [name for name in self.packages if target == name or target.startswith(name + "/")]
        if not names:
            return None
        name = max(names, key=len)
        packages = self.packages[name]
        if len(packages) != 1:
            return None
        directory, package = packages[0]
        subpath = "." + target[len(name):]
        exports = package.get("exports")
        if exports is not None:
            if isinstance(exports, str):
                value = exports if subpath == "." else None
            elif isinstance(exports, dict) and all(key.startswith(".") for key in exports):
                matches = [(key, self.match(key, subpath)) for key in exports]
                matches = [(key, value) for key, value in matches if value is not None]
                if not matches:
                    return None
                key, wildcard = max(matches, key=lambda pair: ("*" not in pair[0], len(pair[0].split("*")[0]), len(pair[0])))
                value = exports[key]
                if isinstance(value, str):
                    value = value.replace("*", wildcard)
            else:
                return None  # Conditional export selection is intentionally unresolved.
            if not isinstance(value, str) or not value.startswith("./"):
                return None
            resolved = local_join(directory, value)
            return [resolved] if resolved and (directory == "." or resolved.startswith(directory + "/")) else None
        if subpath != ".":
            resolved = local_join(directory, subpath[2:])
        else:
            if "module" in package or "browser" in package or "imports" in package:
                return None  # Bundler-specific entry selection is not established.
            value = package.get("main", "index")
            resolved = local_join(directory, value)
        return [resolved] if resolved and (directory == "." or resolved.startswith(directory + "/")) else None
