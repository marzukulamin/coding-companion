"""Read-only Codex hook discovery plus real companion hook execution fixtures.

No model turn, hook trust bypass or global configuration change is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def validate(executable, output):
    from coding_companion.hooks import configuration
    from coding_companion import __version__
    version = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=15, check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="codex-fixture-", dir=ROOT / ".companion") as temporary:
        base = Path(temporary)
        project, state = base / "project", base / "state"
        project.mkdir()
        (project / ".codex").mkdir()
        document = configuration(sys.executable, project, state)
        data = (json.dumps(document, indent=2) + "\n").encode()
        (project / ".codex/hooks.json").write_bytes(data)
        # Inline overrides make discovery independent of project trust; they still
        # require their own normal hook-definition trust before execution.
        overrides = []
        for event, groups in document["hooks"].items():
            handler = groups[0]["hooks"][0]
            fields = ", ".join(f"{key}={json.dumps(value)}" for key, value in handler.items())
            matcher = f'matcher={json.dumps(groups[0]["matcher"])}, ' if "matcher" in groups[0] else ""
            overrides += ["-c", f"hooks.{event}=[{{{matcher}hooks=[{{{fields}}}]}}]"]
        process = subprocess.Popen([str(executable), "app-server", "--listen", "stdio://", *overrides], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=project)
        responses = queue.Queue(maxsize=100)
        def read():
            while True:
                line = process.stdout.readline(1024 * 1024 + 1)
                if not line:
                    return
                try:
                    if len(line) > 1024 * 1024:
                        return
                    responses.put_nowait(json.loads(line))
                except (ValueError, queue.Full):
                    return
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def request(identifier, method, params):
            process.stdin.write((json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode())
            process.stdin.flush()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                message = responses.get(timeout=max(0.01, deadline - time.monotonic()))
                if message.get("id") == identifier:
                    if "error" in message:
                        raise ValueError(message["error"])
                    return message["result"]
            raise TimeoutError(method)
        try:
            request(1, "initialize", {"clientInfo": {"name": "coding-companion-certification", "version": __version__}})
            process.stdin.write(b'{"method":"initialized"}\n')
            process.stdin.flush()
            discovered = request(2, "hooks/list", {"cwds": [str(project)]})
            # Retain only metadata; never request session histories, credentials or turns.
            serialized = json.dumps(discovered)
            if "hook_entry.py" not in serialized:
                raise AssertionError("Companion hook was not discovered by Codex")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()
            reader.join(timeout=2)
            process.stdout.close()
        launcher = ROOT / "src/coding_companion/hook_entry.py"
        (project / "bad.py").write_text("value = (", encoding="utf-8")
        payload = {"hook_event_name": "PostToolUse", "cwd": str(project), "session_id": "synthetic-local-fixture", "tool_input": {"command": "never execute supplied tool input"}}
        command = [sys.executable, str(launcher), "hook", "--project", str(project), "--state-dir", str(state)]
        seeded = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, timeout=30, cwd=project, check=True)
        context = json.loads(json.loads(seeded.stdout)["hookSpecificOutput"]["additionalContext"])
        if not context["observations"] or context["trusted_instructions"] is not False:
            raise AssertionError("Seeded hook diagnostic missing")
        (project / "bad.py").write_text("value = 1", encoding="utf-8")
        clean = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, timeout=30, cwd=project, check=True)
        if json.loads(clean.stdout) != {}:
            raise AssertionError("Clean hook should emit no diagnostic context")
        result = {"status": "passed", "codex": version, "hook_config_sha256": hashlib.sha256(data).hexdigest(), "real_codex_discovery": True, "source_hook_seeded_and_clean_execution": True, "active_turn_delivery": "unverified_requires_user_hook_trust", "trust_bypassed": False, "model_turns_started": 0, "global_config_changed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True, help="Native Codex executable, not a shell shim")
    parser.add_argument("--output", type=Path, default=ROOT / ".companion/codex-validation.json")
    args = parser.parse_args()
    print(json.dumps(validate(args.executable.resolve(), args.output), indent=2))
