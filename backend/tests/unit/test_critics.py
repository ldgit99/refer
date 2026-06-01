from app.agents.critics import consistency_auditor, evidence_critic
from app.citation.matcher import MatchReport
from app.verifier.verify import VerifiedItem


def test_evidence_critic_flags_invalid_doi() -> None:
    verified = {
        "ref-0": VerifiedItem(ref_id="ref-0", status="invalid_doi", severity="CRITICAL")
    }
    verdict = evidence_critic(verified)
    assert not verdict.agree
    assert verdict.severity == "CRITICAL"


def test_evidence_critic_agrees_when_links_open() -> None:
    verified = {
        "ref-0": VerifiedItem(ref_id="ref-0", status="verified", doi_resolves=True),
        "ref-1": VerifiedItem(ref_id="ref-1", status="no_doi"),
    }
    verdict = evidence_critic(verified)
    assert verdict.agree
    assert verdict.severity == "INFO"


def test_consistency_auditor_no_contradiction_on_empty() -> None:
    verdict = consistency_auditor(MatchReport(), {})
    assert verdict.agree
