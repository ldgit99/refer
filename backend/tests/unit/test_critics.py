from app.agents.critics import (
    apa_style_critic,
    consistency_auditor,
    evidence_critic,
)
from app.citation.matcher import MatchReport
from app.verifier.verify import VerifiedItem


def test_evidence_critic_flags_invalid_doi() -> None:
    verified = {
        "ref-0": VerifiedItem(ref_id="ref-0", status="invalid_doi", severity="CRITICAL")
    }
    verdict = evidence_critic(verified)
    assert not verdict.agree
    assert verdict.severity == "CRITICAL"


def test_evidence_critic_downgrades_noted_verified() -> None:
    verified = {
        "ref-0": VerifiedItem(
            ref_id="ref-0", status="verified", confidence=0.95, note="첫 저자 불일치(Lee≠Yi)"
        )
    }
    verdict = evidence_critic(verified)
    assert not verdict.agree


def test_apa_style_critic_clean() -> None:
    verdict = apa_style_critic({"ref-0": "Kim, S. (2024). Title. Journal, 1(1), 1-2."})
    assert verdict.agree


def test_consistency_auditor_no_contradiction_on_empty() -> None:
    verdict = consistency_auditor(MatchReport(), {})
    assert verdict.agree
