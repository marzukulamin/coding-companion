from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Callable

from .common import CompanionError


@dataclass
class Job:
    key: str
    kind: str
    priority: int
    submitted_at: float
    execute: Callable
    payload: object = None


class Scheduler:
    """Bounded lanes, snapshot-key coalescing, and age-based fair selection."""

    def __init__(self, config):
        self.config = config
        self.pending = {}

    def enqueue(self, job: Job):
        if job.kind not in {"fast", "expensive"}:
            raise CompanionError("Unknown scheduler lane")
        if job.key in self.pending:
            return False
        if len(self.pending) >= self.config.max_pending_jobs:
            raise CompanionError("Scheduler backpressure: pending job limit reached")
        self.pending[job.key] = job
        return True

    def choose(self, available: set[str], clock=None):
        clock = time.monotonic() if clock is None else clock
        candidates = [j for j in self.pending.values() if j.kind in available]
        if not candidates:
            return None
        job = min(candidates, key=lambda j: (j.priority - (clock - j.submitted_at) / self.config.aging_seconds, j.submitted_at, j.key))
        del self.pending[job.key]
        return job

    def run(self, on_started, on_finished, cancelled, interrupt=lambda: None):
        limits = {"fast": self.config.max_fast_workers, "expensive": self.config.max_expensive_workers}
        active, counts = {}, {"fast": 0, "expensive": 0}
        pool = ThreadPoolExecutor(max_workers=sum(limits.values()), thread_name_prefix="companion-check")
        try:
            while self.pending or active:
                if cancelled():
                    for job in list(self.pending.values()):
                        on_finished(job, None, None, 0)
                    self.pending.clear()
                available = {kind for kind in counts if counts[kind] < limits[kind]}
                while available and not cancelled():
                    job = self.choose(available)
                    if job is None:
                        break
                    on_started(job)
                    active[pool.submit(job.execute)] = (job, time.monotonic())
                    counts[job.kind] += 1
                    available = {kind for kind in counts if counts[kind] < limits[kind]}
                if not active:
                    continue
                done, _ = wait(active, timeout=0.05, return_when=FIRST_COMPLETED)
                for future in done:
                    job, started = active.pop(future)
                    counts[job.kind] -= 1
                    try:
                        result, error = future.result(), None
                    except Exception as exc:
                        result, error = None, exc
                    on_finished(job, result, error, int((time.monotonic() - started) * 1000))
        except BaseException:
            interrupt()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
