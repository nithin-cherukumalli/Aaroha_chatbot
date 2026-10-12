from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    base, candidate = (
        json.loads(Path(args.baseline).read_text()),
        json.loads(Path(args.candidate).read_text()),
    )
    if base["dataset_sha256"] != candidate["dataset_sha256"]:
        raise SystemExit("Cannot compare runs from different datasets.")
    print(
        json.dumps(
            {
                "baseline": base["run_id"],
                "candidate": candidate["run_id"],
                "baseline_scores": base["scores"],
                "candidate_scores": candidate["scores"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
