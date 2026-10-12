from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evaluations.scoring import score_cases

ROOT = Path(__file__).parents[1]


def load_cases(dataset: str) -> list[dict]:
    path = ROOT / "evaluations" / "datasets" / f"{dataset}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["dev", "test"], required=True)
    parser.add_argument("--mode", choices=["offline", "retrieval", "end-to-end"], required=True)
    args = parser.parse_args()
    if args.mode != "offline" and os.getenv("EVALUATION_LIVE_ENABLED") != "true":
        raise SystemExit(
            "Live evaluation is deliberately blocked. Set EVALUATION_LIVE_ENABLED=true after configuring isolated evaluation database, object prefix, and Qdrant collection."
        )
    cases = load_cases(args.dataset)
    # Offline proves dataset structure and expected actions without making a provider-quality claim.
    outcomes = [
        {
            "case_id": case["case_id"],
            "action": case["expected_action"],
            "evidence_ids": case.get("relevant_evidence_ids", []) if args.mode == "offline" else [],
        }
        for case in cases
    ]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{args.dataset}-{args.mode}"
    folder = ROOT / "evaluation_runs" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "run_id": run_id,
        "mode": args.mode,
        "dataset": args.dataset,
        "timestamp": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(
            (ROOT / "evaluations" / "datasets" / f"{args.dataset}.jsonl").read_bytes()
        ).hexdigest(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        or "unavailable",
        "scores": score_cases(cases, outcomes),
        "limitations": "Offline mode uses expected fixture actions and is not a live retrieval or generation quality result."
        if args.mode == "offline"
        else "Live adapter execution must be completed and reviewed before using results as a release gate.",
    }
    (folder / "per_case.jsonl").write_text("\n".join(json.dumps(row) for row in outcomes) + "\n")
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (folder / "summary.md").write_text(
        f"# Evaluation {run_id}\n\nMode: `{args.mode}`. Cases: {len(cases)}.\n\n{report['limitations']}\n"
    )
    print(folder)


if __name__ == "__main__":
    main()
