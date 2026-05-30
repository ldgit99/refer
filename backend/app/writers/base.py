"""Patch model + Writer protocol (research.md §2.5, plan.md M2 §4)."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

PatchKind = Literal["reference_replace", "citation_comment", "doi_insert"]
PatchSource = Literal["F1", "F2", "F3"]
Severity = Literal["INFO", "WARNING", "CRITICAL"]
OutputMode = Literal["tracked", "annotated", "final"]


class ParagraphRef(BaseModel):
    paragraph_index: int
    char_start: int | None = None
    char_end: int | None = None


class Patch(BaseModel):
    id: str
    kind: PatchKind
    target: ParagraphRef
    before: str = ""
    after: str = ""
    comment: str = ""
    confidence: float = 1.0
    source: PatchSource
    severity: Severity = "INFO"

    @property
    def default_checked(self) -> bool:
        """UI pre-selects high-confidence patches (research.md §9.3)."""
        return self.confidence >= 0.9


class Writer(Protocol):
    """Applies accepted patches to original bytes, returning edited bytes."""

    def apply(
        self,
        data: bytes,
        patches: list[Patch],
        mode: OutputMode = "tracked",
    ) -> bytes: ...
