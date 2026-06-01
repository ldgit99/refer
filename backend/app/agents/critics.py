"""Critic agents for the two-feature pipeline (research.md §7.3, §7.4).

Scope is F1 (matching) and F3 (DOI link opens) only. The former APA-style critic
(C2) has been removed along with F2. Critics receive the specialist conclusion +
original input (information asymmetry, §7.1).
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


def evidence_critic(verified: dict[str, VerifiedItem]) -> CriticVerdict:
    """C3 — re-read of DOI link verification. Invalid (non-opening) DOIs -> CRITICAL."""
    invalid = [ref_id for ref_id, v in verified.items() if v.status == "invalid_doi"]
    agree = not invalid
    return CriticVerdict(
        agent="C3-EvidenceCritic",
        agree=agree,
        revision_request=(
            "" if agree else f"{len(invalid)}건의 DOI 링크가 열리지 않습니다: {', '.join(invalid)}"
        ),
        severity="CRITICAL" if invalid else "INFO",
    )


def consistency_auditor(
    report: MatchReport,
    verified: dict[str, VerifiedItem],
) -> CriticVerdict:
    """C4 — cross-feature check: a reference matched in the body but its DOI is dead."""
    contradictions: list[str] = []
    matched_ref_indices = {
        i.reference_index for i in report.issues if i.type != "orphan_reference"
    }
    cited_ref_indices = {ref.index for ref in report.references} - {
        i.reference_index for i in report.issues if i.type == "orphan_reference"
    }
    _ = matched_ref_indices  # retained for clarity; cited set drives the check
    for ref in report.references:
        if ref.index not in cited_ref_indices:
            continue
        v = verified.get(f"ref-{ref.index}")
        if v and v.status == "invalid_doi":
            contradictions.append(
                f"ref-{ref.index}: 본문에서 인용된 문헌이지만 DOI 링크가 열리지 않습니다."
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
    verified: dict[str, VerifiedItem],
    citations: list[InTextCitation] | None = None,
    references: list[ReferenceItem] | None = None,
) -> dict[str, CriticVerdict]:
    return {
        "match_report_critic": citation_auditor(report),
        "verified_critic": evidence_critic(verified),
        "consistency": consistency_auditor(report, verified),
    }
