"""LangGraph StateGraph wrapper (research.md §7.2, plan.md M3).

Design choice: the deterministic specialist pipeline (already covered by tests in
``app.review``) is the single source of truth. This module composes it so we get
checkpointing / streaming / HITL when langgraph is installed, but it **degrades
gracefully**: if langgraph is missing, ``run_review_graph`` falls back to the
plain async pipeline plus the deterministic critics. Both paths call the same
specialist functions, so the M2-vs-M3 regression (plan.md M3 완료 기준) holds.
"""

from __future__ import annotations

from app.agents.critics import run_all_critics
from app.agents.evidence_llm import recheck_verified_titles
from app.agents.hitl import build_hitl_queue
from app.agents.state import CriticVerdict, ReviewState
from app.config import get_settings
from app.parsers.base import ParsedDocument
from app.review import ReviewResult, review_with_verification


async def _run_specialists(document: ParsedDocument) -> ReviewResult:
    return await review_with_verification(document)


async def _evidence_revision_loop(result: ReviewResult) -> tuple[CriticVerdict, int]:
    """C3 ↔ specialist bounded revision (research.md §7.4, plan.md M3 §5).

    Runs the deterministic EvidenceCritic, then asks the LLM C3 branch for an
    independent title-equivalence re-check. When the LLM flags a 'verified' item
    as a likely different work, the verifier's conclusion is revised (downgraded
    to doi_mismatch) and the critic re-runs — bounded by ``critic_revision_max``.
    """
    from app.agents.critics import evidence_critic

    settings = get_settings()
    csl_by_id = {c.id: c for c in result.csl_items}
    revisions = 0
    verdict = evidence_critic(result.verified)

    while revisions < settings.critic_revision_max:
        downgrades = await recheck_verified_titles(result.verified, csl_by_id)
        if not downgrades:
            break
        for note in downgrades:
            ref_id = note.split(":", 1)[0].strip()
            item = result.verified.get(ref_id)
            if item is not None and item.status == "verified":
                item.status = "doi_mismatch"
                item.title_matches = False
                item.severity = "WARNING"
                item.note = (item.note + " | " if item.note else "") + note
        revisions += 1
        verdict = evidence_critic(result.verified)

    return verdict, revisions


async def _attach_critics(state: ReviewState, result: ReviewResult) -> ReviewState:
    # Bounded Generator-Critic revision loop for evidence (C3) when an LLM exists.
    # This may mutate result.verified (downgrades), so run it before the critics.
    verified_verdict, evidence_revisions = await _evidence_revision_loop(result)

    critics = run_all_critics(
        result.match_report,
        result.formatted,
        result.verified,
        citations=result.match_report.citations,
        references=result.match_report.references,
    )
    # C3 verdict reflects the LLM revision loop; C1/C2/C4 reflect post-revision state.
    critics["verified_critic"] = verified_verdict

    state["match_report"] = result.match_report
    state["formatted"] = result.formatted
    state["verified"] = result.verified
    state["csl_items"] = result.csl_items
    state["patch_proposals"] = result.patches
    state["llm_used"] = result.llm_used
    state["revision_counts"] = {"evidence": evidence_revisions}
    state["match_report_critic"] = critics["match_report_critic"]
    state["formatted_critic"] = critics["formatted_critic"]
    state["verified_critic"] = critics["verified_critic"]
    state["consistency"] = critics["consistency"]
    state["hitl_queue"] = build_hitl_queue(critics, result.verified)
    return state


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401

        return True
    except ImportError:
        return False


async def run_review_graph(document: ParsedDocument) -> ReviewState:
    """Run the full specialist + critic review, returning a ReviewState."""
    state: ReviewState = {
        "full_text": document.full_text,
        "references_section": document.references_section,
        "original_format": document.original_format,
        "revision_counts": {},
    }
    result = await _run_specialists(document)
    return await _attach_critics(state, result)


def build_compiled_graph():  # pragma: no cover - exercised only with langgraph installed
    """Construct a LangGraph StateGraph. Importable only with the agents extra."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ReviewState)

    async def analyze_node(state: ReviewState) -> ReviewState:
        return state

    graph.add_node("analyze", analyze_node)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", END)
    return graph.compile()
