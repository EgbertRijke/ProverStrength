"""Isolated driver for the frozen evaluator; never loads the live product tree.

This file is copied into each measurement's evidence and executed without site
packages. It deliberately imports the evaluator only after selecting its frozen
source directory. No publishing credentials belong in this process environment.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                result[str(path.relative_to(root))] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    return result


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main(root: Path) -> None:
    request = json.loads((root / "request.json").read_text())
    metadata = json.loads((root / "observation.json").read_text())
    evaluator = root / "evaluator"
    sys.path.insert(0, str(evaluator / "src"))
    from prover_strength.cli import markdown
    from prover_strength.data import digest
    from prover_strength.model import rate
    from prover_strength.runner import file_sha256, run

    suite = json.loads((evaluator / request["suite_path"]).read_text())
    if digest(suite) != metadata["suite_id"]:
        raise ValueError("frozen suite changed")
    provers = json.loads((root / "provers.json").read_text())
    profile = metadata["profile"]
    result = run(
        suite,
        provers,
        agda=request["agda"],
        budget=request["budget"],
        environment_id=metadata["environment"]["id"],
        seeds=profile["seeds"],
        artifacts=root / "artifacts",
        order_seed=profile["order_seed"],
        reference_budget=profile["reference_check_budget_seconds"],
        max_output=profile["max_output_bytes"],
    )
    for name, before in metadata["source_hashes"].items():
        if hashes(root / name) != before:
            raise ValueError("frozen sources changed during measurement")
    save(root / "results.json", result)
    try:
        report = rate(result, request["anchor"], bootstrap=200, seed=0)
        rendered = markdown(report)
    except ValueError as error:
        if "disconnected" not in str(error).lower():
            raise
        report = {
            "schema_version": "prover-strength.unidentified-rating.v1",
            "input_sha256": digest(result),
            "method": "conditional-rasch-bt-v1",
            "prior_sd_points": 800.0,
            "warnings": [str(error)],
            "separation": False,
        }
        rendered = (
            "# Unidentified rating\n\n"
            + str(error)
            + "\n\nAll task outcomes are retained.\n"
        )
    save(root / "ratings.json", report)
    (root / "report.md").write_text(rendered, encoding="utf-8")
    save(
        root / "completed.json",
        {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source_integrity": "unchanged",
            "results_sha256": file_sha256(str(root / "results.json")),
            "ratings_sha256": file_sha256(str(root / "ratings.json")),
        },
    )
    print(rendered, flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
