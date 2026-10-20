from __future__ import annotations

import os
from pathlib import Path

from .common import CompanionError, atomic_write, canonical, now


class Busy(CompanionError):
    pass


class Ownership:
    """Nonblocking OS lock. PID/heartbeat metadata never grants ownership."""

    def __init__(self, state: Path):
        self.state = state
        self.handle = None

    def __enter__(self):
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.state.is_symlink() or self.state.is_junction():
            raise CompanionError("State directory cannot be linked")
        lock = self.state / "coordinator.lock"
        if lock.is_symlink():
            raise CompanionError("Coordinator lock cannot be linked")
        self.handle = lock.open("a+b")
        # Windows byte locks deny even reads by another handle. Inspect length,
        # never the locked byte, before attempting the nonblocking lock.
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise Busy("Coordinator already owns this project; use mailbox") from exc
        try:
            atomic_write(self.state / "owner.json", canonical({"pid": os.getpid(), "started_at": now()}).encode())
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *args):
        if self.handle:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None
