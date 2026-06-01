"""C3 EvidenceCritic LLM branch — semantic title-equivalence re-check.

The deterministic EvidenceCritic only compares fuzzy title strings. When an LLM
is configured, this independently judges whether a ``verified`` reference truly
matches the resolver/Crossref title, catching cases where surface strings differ
but the work is (or is not) the same (research.md §7.4, §7.8 hallucination guard).
Best-effort: any failure leaves the deterministic verdict untouched.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from app.citation.csl import CSLItem
from app.llm import ChatMessage, chat_json, llm_configured
from app.verifier.verify import VerifiedItem


class _TitleJudgement(BaseModel):
    same_work: bool = True
    reason: str = ""


def _prompt(ref_title: str, matched_title: str) -> list[ChatMessage]:
    return [
        {
            "role": "developer",
            "content": (
                "You judge whether two bibliographic titles refer to the same "
                "scholarly work. Account for translation, subtitle, and "
                "abbreviation differences. Return JSON only: "
                '{"same_work": true|false, "reason": "short"}.'
            ),
        },
        {
            "role": "user",
            "content": f"Reference title: {ref_title}\nCandidate title: {matched_title}",
        },
    ]


async def recheck_verified_titles(
    verified: dict[str, VerifiedItem],
    csl_by_id: dict[str, CSLItem],
    *,
    chat=chat_json,
    max_checks: int = 12,
) -> list[str]:
    """Return downgrade notes for 'verified' items the LLM deems different works."""
    if not llm_configured():
        return []
    downgrades: list[str] = []
    checked = 0
    for ref_id, item in verified.items():
        if checked >= max_checks:
            break
        if item.status != "verified" or not item.matched_title:
            continue
        ref = csl_by_id.get(ref_id)
        if ref is None or not ref.title:
            continue
        checked += 1
        try:
            payload = await chat(_prompt(ref.title, item.matched_title))
            judgement = _TitleJudgement.model_validate(payload)
        except (ValidationError, RuntimeError, ValueError):
            continue
        if not judgement.same_work:
            downgrades.append(
                f"{ref_id}: LLM 판정상 다른 문헌일 수 있음 ({judgement.reason or 'title mismatch'})"
            )
    return downgrades
