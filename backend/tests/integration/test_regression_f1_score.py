"""Regression F1 score over the synthetic corpus (plan.md M7 완료 기준 ≥ 0.9).

Treats each expected issue-type count in the corpus as the ground-truth positive
set per case, runs the deterministic F1 matcher, and computes a micro-averaged
F1 across all cases. This locks in matcher accuracy and gives a single number to
track as the matcher evolves.
"""

import json
from pathlib import Path

from app.citation.extractor import extract_from_text
from app.citation.matcher import match
from app.citation.references import parse_references
from app.parsers.base import build_document

CORPUS = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "corpus.json").read_text(
        encoding="utf-8"
    )
)

_ISSUE_KEYS = (
    "orphan_citation",
    "orphan_reference",
    "year_mismatch",
    "author_count_mismatch",
    "duplicate_reference",
)


def _run(paragraphs: list[str]):
    document = build_document(paragraphs)
    citations = []
    for para in document.body_paragraphs():
        citations.extend(extract_from_text(para.text, para.index))
    references = parse_references(document.references_section)
    return match(citations, references)


def test_corpus_f1_score_above_threshold() -> None:
    tp = fp = fn = 0
    for case in CORPUS["cases"]:
        report = _run(case["paragraphs"])
        stats = report.stats
        expected = case["expected"]
        for key in _ISSUE_KEYS:
            exp = int(expected.get(key, 0))
            got = int(stats.get(key, 0))
            tp += min(exp, got)
            fp += max(0, got - exp)
            fn += max(0, exp - got)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 1.0

    assert f1 >= 0.9, (
        f"F1={f1:.3f} (precision={precision:.3f}, recall={recall:.3f}, "
        f"tp={tp}, fp={fp}, fn={fn})"
    )
