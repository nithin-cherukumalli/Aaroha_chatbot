from __future__ import annotations

from collections import Counter
from typing import Any


def score_cases(cases: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {row["case_id"]: row for row in outcomes}
    answerable = [case for case in cases if case["expected_action"] in {"answer", "partial_answer"}]
    unsupported = [case for case in cases if case["expected_action"] == "abstain"]
    correct_action = sum(
        by_id.get(case["case_id"], {}).get("action") == case["expected_action"] for case in cases
    )
    hit = sum(
        bool(
            set(by_id.get(case["case_id"], {}).get("evidence_ids", []))
            & set(case.get("relevant_evidence_ids", []))
        )
        for case in answerable
    )
    abstained = sum(
        by_id.get(case["case_id"], {}).get("action") == "abstain" for case in unsupported
    )
    return {
        "case_count": len(cases),
        "action_accuracy": {"numerator": correct_action, "denominator": len(cases)},
        "retrieval_hit_at_5": {"numerator": hit, "denominator": len(answerable)},
        "appropriate_abstention": {"numerator": abstained, "denominator": len(unsupported)},
        "categories": dict(Counter(case["category"] for case in cases)),
        "note": "Retrieval and answer quality scores are meaningful only for live runs with reviewed evidence; offline outcomes check structure, not model quality.",
    }
