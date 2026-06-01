"""Job store with original/edited file blobs and TTL (research.md §6.1, §12.13).

Default is in-process (fine for a single-worker demo). On serverless / multi-
instance deployments the in-memory store loses jobs between the upload request
and a later ``/apply`` or ``/download`` that lands on a different instance. To
fix that, the store is **pluggable**: when ``REDIS_URL`` points at a reachable
Redis (and the ``redis`` package is installed), job state is persisted there so
any instance can serve it. If Redis is unavailable it transparently falls back
to the in-memory store, so local dev and the keyless demo keep working.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from app.agents.state import ConflictItem, CriticVerdict
from app.config import get_settings
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

    # --- serialization for external backends ---
    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "filename": self.filename,
                "original_format": self.original_format,
                "status": self.status,
                "created_at": self.created_at,
                "original_b64": _b64(self.original_bytes),
                "edited_b64": _b64(self.edited_bytes),
                "output_format": self.output_format,
                "result": self.result.model_dump(mode="json") if self.result else None,
                "critics": {k: v.model_dump(mode="json") for k, v in self.critics.items()},
                "hitl_queue": [c.model_dump(mode="json") for c in self.hitl_queue],
                "applied_patch_ids": sorted(self.applied_patch_ids),
                "error": self.error,
                "events": self.events,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> Job:
        d = json.loads(raw)
        return cls(
            id=d["id"],
            filename=d["filename"],
            original_format=d["original_format"],
            status=d["status"],
            created_at=d["created_at"],
            original_bytes=_unb64(d.get("original_b64")),
            edited_bytes=_unb64(d.get("edited_b64")),
            output_format=d.get("output_format"),
            result=ReviewResult.model_validate(d["result"]) if d.get("result") else None,
            critics={
                k: CriticVerdict.model_validate(v) for k, v in (d.get("critics") or {}).items()
            },
            hitl_queue=[ConflictItem.model_validate(c) for c in (d.get("hitl_queue") or [])],
            applied_patch_ids=set(d.get("applied_patch_ids") or []),
            error=d.get("error"),
            events=d.get("events") or [],
        )


def _b64(b: bytes | None) -> str | None:
    return base64.b64encode(b).decode("ascii") if b is not None else None


def _unb64(s: str | None) -> bytes | None:
    return base64.b64decode(s) if s else None


class JobStore:
    """In-memory store (default backend)."""

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

    def save(self, job: Job) -> None:  # no-op: in-memory jobs are mutated in place
        self._jobs[job.id] = job

    def add_event(self, job_id: str, phase: str, detail: str = "") -> None:
        job = self.get(job_id)
        if job:
            job.events.append({"phase": phase, "detail": detail, "ts": time.time()})
            self.save(job)


class RedisJobStore(JobStore):
    """Redis-backed store: durable across instances. Persists on every save."""

    def __init__(self, client) -> None:
        super().__init__()
        self._redis = client

    @staticmethod
    def _key(job_id: str) -> str:
        return f"refer:job:{job_id}"

    def create(self, filename: str, original_format: str, data: bytes) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(
            id=jid,
            filename=filename,
            original_format=original_format,
            original_bytes=data,
        )
        self.save(job)
        return job

    def get(self, job_id: str) -> Job | None:
        raw = self._redis.get(self._key(job_id))
        if raw is None:
            return None
        job = Job.from_json(raw if isinstance(raw, str) else raw.decode("utf-8"))
        if job.is_expired():
            self._redis.delete(self._key(job_id))
            return None
        return job

    def save(self, job: Job) -> None:
        self._redis.set(self._key(job.id), job.to_json(), ex=TTL_SECONDS)

    def add_event(self, job_id: str, phase: str, detail: str = "") -> None:
        job = self.get(job_id)
        if job:
            job.events.append({"phase": phase, "detail": detail, "ts": time.time()})
            self.save(job)


def _build_store() -> JobStore:
    settings = get_settings()
    url = settings.redis_url
    # Only attempt Redis when a non-localhost URL is configured (i.e. a real
    # provisioned instance); the localhost default is treated as "in-memory".
    if url and "localhost" not in url and "127.0.0.1" not in url:
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            return RedisJobStore(client)
        except Exception:  # noqa: BLE001 - fall back to in-memory on any failure
            pass
    return JobStore()


@lru_cache
def get_job_store() -> JobStore:
    return _build_store()
