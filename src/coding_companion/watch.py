from __future__ import annotations

import sys
import time

from .common import canonical
from .discovery import InventoryCache, snapshot
from .mailbox import Mailbox
from .maintenance import maintain


def watch(engine, dispatch, should_stop, *, once: bool = False, max_seconds: float | None = None):
    store = engine.store
    mailbox = Mailbox(store, dispatch)
    maintain(store)
    started = time.monotonic()
    last = snapshot(store.root, store.config, store.state).snapshot_id
    inventory = InventoryCache()
    candidate, changed_at = None, None
    maintenance_at = time.monotonic()
    # Establish a baseline; static checks only. Native probes need explicit requests.
    baseline = engine.check()
    print(canonical({"event": "baseline", "snapshot_id": baseline["snapshot_id"], "status": baseline["status"]}), file=sys.stderr, flush=True)
    while not should_stop():
        mailbox.drain()
        if time.monotonic() - maintenance_at > 60:
            maintain(store)
            maintenance_at = time.monotonic()
        if once or should_stop() or (max_seconds is not None and time.monotonic() - started >= max_seconds):
            break
        current = inventory.read(store.root, store.config, store.state).snapshot_id
        if current == last:
            candidate, changed_at = None, None
        elif current != candidate:
            candidate, changed_at = current, time.monotonic()
        elif time.monotonic() - changed_at >= store.config.debounce_seconds:
            report = engine.check(scope="changed")
            print(canonical({"event": "settled_change", "snapshot_id": report["snapshot_id"], "status": report["status"], "detection_ms": int((time.monotonic() - changed_at) * 1000)}), file=sys.stderr, flush=True)
            last, candidate, changed_at = current, None, None
        time.sleep(store.config.poll_seconds)
    return {"status": "stopped", "completeness": "complete", "delivery": "cli_checkpoints"}
