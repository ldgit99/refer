"""Pydantic request/response schemas for the public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.state import ConflictItem, CriticVerdict
from app.citation.matcher import MatchReport
from app.verifier.verify import VerifiedItem
from app.writers.base import OutputMode, Patch


class JobCreated(BaseModel):
    job_id: str
    status: str


class JobResult(BaseModel):
    """Review result payload (synchronous in M1, job-bound from M2)."""

    job_id: str | None = None
    filename: str
    original_format: str
    status: str = "done"
    match_report: MatchReport
    formatted: dict[str, str] = Field(default_factory=dict)
    verified: dict[str, VerifiedItem] = Field(default_factory=dict)
    patches: list[Patch] = Field(default_factory=list)
    critics: dict[str, CriticVerdict] = Field(default_factory=dict)
    hitl_queue: list[ConflictItem] = Field(default_factory=list)
    llm_used: bool = False


class ApplyRequest(BaseModel):
    accepted_patch_ids: list[str] = Field(default_factory=list)
    mode: OutputMode = "tracked"


class ApplyResponse(BaseModel):
    job_id: str
    applied: int
    download_url: str


class HitlResponse(BaseModel):
    job_id: str
    conflicts: list[ConflictItem] = Field(default_factory=list)


class HitlResolveRequest(BaseModel):
    conflict_id: str
    choice: Literal["specialist", "critic"]


class HitlResolveResponse(BaseModel):
    job_id: str
    conflict_id: str
    resolved: bool
