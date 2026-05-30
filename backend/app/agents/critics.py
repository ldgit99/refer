"""Critic agents (research.md §7.3 Critic table, §7.4 protocol).

All critics here are the deterministic baseline. The LLM-assisted branches
(C2 non-standard types, C3 semantic title equivalence) activate only when an API
key is present; otherwise the deterministic verdict stands. Critics receive the
specialist *conclusion + original input*, never the specialist's reasoning
(information asymmetry, §7.1).
"""

from __future__ import annotations

from app.agents.state import CriticVerdict
from app.citation.extractor import InTextCitation
from app.citation.matcher import MatchReport
from app.citation.references import ReferenceItem
from app.verifier.verify import VerifiedItem


def citation_auditor(report: MatchReport) -> CriticVerdict:
    """C1 — stricter re-check of F1, especially et al. and duplicate citations."""
    extra_issues = 0
    for cit in report.citations:
        if cit.style in {"author_year", "narrative"} and len(cit.authors) >= 3:
            if "et al" not in cit.raw.lower() and "외" not in cit.raw:
                extra_issues += 1
    agree = extra_issues == 0
    return CriticVerdict(
        agent="C1-CitationAuditor",
        agree=agree,
        revision_request=(
            "" if agree else f"{extra_issues}건의 et al. 규칙 위반 의심 인용을 재검토하세요."
        ),
        severity="WARNING" if not agree else "INFO",
    )


def apa_style_critic(formatted: dict[str, str]) -> CriticVerdict:
    """C2 — APA 7 rule checks on formatted strings."""
    problems: list[str] = []
    for ref_id, text in formatted.items():
        if not text:
            continue
        if " and " in text and "&" not in text:
            problems.append(f"{ref_id}: 저자 구분에 '&' 대신 'and' 사용")
        if "(n.d.)" in text:
            problems.append(f"{ref_id}: 연도 누락")
    agree = not problems
    return CriticVerdict(
        agent="C2-APAStyleCritic",
        agree=agree,
        revision_request="; ".join(problems),
        severity="INFO",
    )


def evidence_critic(verified: dict[str, VerifiedItem]) -> CriticVerdict:
    """C3 — independent re-read of verification results (hallucination guard).

    Downgrades any 'verified' that the verifier itself noted disagreements on,
    and surfaces invalid DOIs as CRITICAL.
    """
    downgrades: list[str] = []
    critical = False
    for ref_id, v in verified.items():
        if v.status == "verified" and v.note:
            downgrades.append(f"{ref_id}: '{v.note}' 근거로 WARNING 강등 권고")
        if v.status == "invalid_doi":
            critical = True
    agree = not downgrades and not critical
    return CriticVerdict(
        agent="C3-EvidenceCritic",
        agree=agree,
        revision_request="; ".join(downgrades),
        severity="CRITICAL" if critical else ("WARNING" if downgrades else "INFO"),
    )


def consistency_auditor(
    report: MatchReport,
    verified: dict[str, VerifiedItem],
) -> CriticVerdict:
    """C4 — cross-stage contradiction check (F1 matched but F3 not_found, etc.)."""
    contradictions: list[str] = []
    matched_ref_indices = {
        i.reference_index for i in report.issues if i.type != "orphan_reference"
    }
    for ref in report.references:
        if ref.index in matched_ref_indices:
            continue
        v = verified.get(f"ref-{ref.index}")
        if v and v.status == "not_found":
            contradictions.append(
                f"ref-{ref.index}: 본문 인용과 매칭됐으나 외부 검증 실패(not_found)"
            )
    agree = not contradictions
    return CriticVerdict(
        agent="C4-ConsistencyAuditor",
        agree=agree,
        revision_request="; ".join(contradictions),
        severity="WARNING" if contradictions else "INFO",
    )


def run_all_critics(
    report: MatchReport,
    formatted: dict[str, str],
    verified: dict[str, VerifiedItem],
    citations: list[InTextCitation] | None = None,
    references: list[ReferenceItem] | None = None,
) -> dict[str, CriticVerdict]:
    return {
        "match_report_critic": citation_auditor(report),
        "formatted_critic": apa_style_critic(formatted),
        "verified_critic": evidence_critic(verified),
        "consistency": consistency_auditor(report, verified),
    }
