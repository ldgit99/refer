"""ReviewState — the LangGraph state model (research.md §7.6).

Implemented as a TypedDict (LangGraph-friendly) plus CriticVerdict / ConflictItem
models used by the Generator-Critic protocol (§7.4).
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from app.citation.csl import CSLItem
from app.citation.extractor import InTextCitation
from app.citation.matcher import MatchReport
from app.citation.references import ReferenceItem
from app.verifier.verify import VerifiedItem
from app.writers.base import Patch


class CriticVerdict(BaseModel):
    agent: str
    agree: bool = True
    revision_request: str = ""
    evidence: dict = Field(default_factory=dict)
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"


class ConflictItem(BaseModel):
    id: str
    stage: str
    specialist_claim: str
    critic_claim: str
    evidence: dict = Field(default_factory=dict)
    resolved: bool = False
    resolution: str | None = None


class ReviewState(TypedDict, total=False):
    # Phase 1
    raw_bytes: bytes
    filename: str
    original_format: str
    full_text: str
    references_section: str | None
    # Phase 2
    citations: list[InTextCitation]
    references: list[ReferenceItem]
    csl_items: list[CSLItem]
    match_report: MatchReport
    match_report_critic: CriticVerdict
    formatted: dict[str, str]
    formatted_critic: CriticVerdict
    # Phase 3
    verified: dict[str, VerifiedItem]
    verified_critic: CriticVerdict
    # Final
    consistency: CriticVerdict
    hitl_queue: list[ConflictItem]
    revision_counts: dict[str, int]
    llm_used: bool
    # D1
    patch_proposals: list[Patch]
    accepted_patches: list[str]
    output_mode: Literal["tracked", "annotated", "final"]
    output_file_path: str | None
