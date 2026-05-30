"""Regression set (plan.md M7 §5).

Runs the F1 deterministic pipeline over the synthetic corpus in
tests/fixtures/corpus.json and asserts the expected MatchReport stats. Real
binary KCI/SCI fixtures can be added later by dropping files in fixtures/ and a
parser branch; the assertions here lock in F1 behaviour against drift.
"""

import json
from pathlib import Path

import pytest

from app.citation.extractor import extract_from_text
from app.citation.matcher import match
from app.citation.references import parse_references
from app.parsers.base import build_document

CORPUS = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "corpus.json").read_text(
        encoding="utf-8"
    )
)


def _run_case(paragraphs: list[str]):
    document = build_document(paragraphs)
    citations = []
    for para in document.body_paragraphs():
        citations.extend(extract_from_text(para.text, para.index))
    references = parse_references(document.references_section)
    return match(citations, references)


@pytest.mark.parametrize("case", CORPUS["cases"], ids=[c["id"] for c in CORPUS["cases"]])
def test_corpus_case(case: dict) -> None:
    report = _run_case(case["paragraphs"])
    stats = report.stats
    for key, expected in case["expected"].items():
        assert stats.get(key, 0) == expected, (
            f"[{case['id']}] {key}: expected {expected}, got {stats.get(key, 0)} "
            f"(issues={[i.type for i in report.issues]})"
        )


def test_corpus_has_ten_cases() -> None:
    # plan.md M7: KCI 5 + SCI 3 + problem cases 2 == 10 representative cases.
    assert len(CORPUS["cases"]) >= 10
