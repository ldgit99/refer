"""Pydantic request/response schemas for the public API."""

from __future__ import annotations

from pydantic import BaseModel

from app.citation.matcher import MatchReport


class JobResult(BaseModel):
    """Synchronous review result returned by ``POST /jobs`` in M1.

    From M2 onward this becomes asynchronous (job_id + SSE), but the
    ``match_report`` payload shape is preserved.
    """

    filename: str
    original_format: str
    match_report: MatchReport
