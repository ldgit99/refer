"""HITL escalation (research.md §7.3 O2, §9.3 #5).

Turns unresolved critic↔specialist conflicts and low-confidence verifications
into ConflictItems for the user to decide.
"""

from __future__ import annotations

from app.agents.state import ConflictItem, CriticVerdict
from app.config import get_settings
from app.verifier.verify import VerifiedItem


def build_hitl_queue(
    critics: dict[str, CriticVerdict],
    verified: dict[str, VerifiedItem],
) -> list[ConflictItem]:
    settings = get_settings()
    queue: list[ConflictItem] = []

    for key, verdict in critics.items():
        if not verdict.agree and verdict.severity in {"WARNING", "CRITICAL"}:
            queue.append(
                ConflictItem(
                    id=f"hitl-{key}",
                    stage=verdict.agent,
                    specialist_claim="(자동 판정 결과)",
                    critic_claim=verdict.revision_request,
                    evidence=verdict.evidence,
                )
            )

    for ref_id, v in verified.items():
        if v.confidence and v.confidence < settings.hitl_confidence_gate:
            if v.status in {"doi_mismatch", "not_found"}:
                queue.append(
                    ConflictItem(
                        id=f"hitl-{ref_id}",
                        stage="C3-EvidenceCritic",
                        specialist_claim=f"status={v.status}",
                        critic_claim=v.note or "신뢰도 낮음 — 사용자 확인 필요",
                        evidence={"confidence": v.confidence},
                    )
                )
    return queue
