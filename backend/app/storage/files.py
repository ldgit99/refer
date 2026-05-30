"""In-memory job store with original/edited file blobs and TTL (research.md §12.13).

Single-process default for the demo. The interface is intentionally small so it
can be swapped for Redis-backed storage when the arq queue lands in production.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from app.agents.state import ConflictItem, CriticVerdict
from app.review import ReviewResult

JobStatus = Literal["pending", "processing", "done", "applied", "error"]
TTL_SECONDS = 24 * 60 * 60


@dataclass
class Job:
    id: str
    filename: str
    original_format: str
    status: JobStatus = "pending"
    created_at: float = field(default_factory=time.time)
    original_bytes: bytes | None = None
    edited_bytes: bytes | None = None
    output_format: str | None = None  # may differ from original (hwp -> hwpx)
    result: ReviewResult | None = None
    critics: dict[str, CriticVerdict] = field(default_factory=dict)
    hitl_queue: list[ConflictItem] = field(default_factory=list)
    applied_patch_ids: set[str] = field(default_factory=set)
    error: str | None = None
    events: list[dict] = field(default_factory=list)

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > TTL_SECONDS


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def _gc(self) -> None:
        for jid in [j for j, job in self._jobs.items() if job.is_expired()]:
            self._jobs.pop(jid, None)

    def create(self, filename: str, original_format: str, data: bytes) -> Job:
        self._gc()
        jid = uuid.uuid4().hex[:12]
        job = Job(
            id=jid,
            filename=filename,
            original_format=original_format,
            original_bytes=data,
        )
        self._jobs[jid] = job
        return job

    def get(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job and job.is_expired():
            self._jobs.pop(job_id, None)
            return None
        return job

    def add_event(self, job_id: str, phase: str, detail: str = "") -> None:
        job = self.get(job_id)
        if job:
            job.events.append({"phase": phase, "detail": detail, "ts": time.time()})


@lru_cache
def get_job_store() -> JobStore:
    return JobStore()
