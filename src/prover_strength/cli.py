"""Command line for portable rating, portable Agda tasks, and reproducible demos."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

from .benchmark import smoke_suite
from .data import SCHEMA, digest, merge
from .model import SCALE, logistic, rate
from .process import MAX_OUTPUT


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def markdown(report: dict[str, Any]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Portable prover rating",
        "",
        f"Track: `{cell(report['protocol']['track'])}`; "
        f"budget: {report['protocol']['budget_seconds']} seconds; anchor: "
        f"{cell(report['anchor']['id'])} = 1500.",
        "",
        "A 400-point advantage represents 10:1 model odds of being the sole solver, "
        "conditional on exactly one of the two provers solving a matched task.",
        "",
        "| Prover | Rating | Family bootstrap 95% interval | Balanced solved |",
        "| --- | ---: | --- | ---: |",
    ]
    for row in report["ratings"]:
        interval = row["interval95"]
        text = f"{interval[0]:.0f}–{interval[1]:.0f}" if interval else "unavailable"
        if row["anchor"]:
            text = "fixed reference"
        lines.append(
            f"| {cell(row['prover'])} | {row['rating']:.0f} | {text} | {row['balanced_solve_rate']:.1%} |"
        )
    domains = sorted(report["ratings"][0]["solve_rate_by_domain"])
    lines += [
        "",
        "Domain solve rates (equal weight per family):",
        "",
        "| Prover | " + " | ".join(cell(d) for d in domains) + " |",
        "| --- | " + " | ".join("---:" for _ in domains) + " |",
    ]
    for row in report["ratings"]:
        lines.append(
            "| "
            + cell(row["prover"])
            + " | "
            + " | ".join(f"{row['solve_rate_by_domain'][d]:.1%}" for d in domains)
            + " |"
        )
    lines += [
        "",
        f"Independent sampling units: {report['family_count']} families. "
        f"Bootstrap draws: {report['bootstrap']['draws']}. "
        f"Maximum rating shift on doubling the prior SD: {report['prior_sensitivity_max_shift_points']:.1f} points.",
        "",
    ]
    if report["warnings"]:
        lines.extend("- " + message for message in report["warnings"])
        lines.append("")
    lines += [
        "Intervals describe sampling variability of the regularized estimate on the declared "
        "family population. They are not guarantees about unseen domains. The anchor's "
        "zero-width interval is a convention, not perfect knowledge of its performance.",
        "",
        f"Suite fingerprint: `{report['suite_id']}`.",
        f"Results fingerprint: `{report['input_sha256']}`.",
        "",
    ]
    return "\n".join(lines)


def simulated(*, seed: int = 7, families_per_domain: int = 50) -> dict[str, Any]:
    """Independent synthetic Bernoulli responses, with shared task difficulties."""
    rng = random.Random(seed)
    abilities = {
        "simulated-reference": 1500,
        "simulated-strong": 1800,
        "simulated-weak": 1200,
    }
    tasks, rows = [], []
    for domain in ("logic", "equality", "induction", "dependent"):
        for family in range(families_per_domain):
            difficulty = rng.gauss(1500, 450)
            family_id = f"{domain}-{family}"
            for variant in range(3):
                task_id = f"{family_id}-{variant}"
                d = difficulty + rng.gauss(0, 60)
                tasks.append(
                    {
                        "id": task_id,
                        "domain": domain,
                        "family": family_id,
                        "sha256": digest(task_id),
                    }
                )
                for name, ability in abilities.items():
                    success = rng.random() < logistic((ability - d) / SCALE)
                    rows.append(
                        {
                            "prover": name,
                            "task": task_id,
                            "seed": 0,
                            "status": "verified" if success else "timeout",
                            "elapsed_seconds": 1.0 if success else 10.0,
                            "checker_accepted": success,
                            "artifact_sha256": "simulated-not-a-proof"
                            if success
                            else None,
                        }
                    )
    return {
        "schema_version": SCHEMA,
        "suite_id": digest(tasks),
        "tasks": tasks,
        "seeds": [0],
        "protocol": {
            "track": "SIMULATION-v1",
            "budget_seconds": 10.0,
            "environment_id": "simulation",
            "checker_id": "none-simulation",
            "enforcement": "none-simulation",
            "synthetic": True,
        },
        "provers": [{"id": name, "revision": "simulation-v1"} for name in abilities],
        "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prover-strength")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser(
        "generate", help="write a self-contained public smoke suite"
    )
    generate.add_argument("output", type=Path)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--variants", type=int, default=2)
    check = commands.add_parser(
        "check-suite", help="check all reference proofs in fresh Agda processes"
    )
    check.add_argument("suite", type=Path)
    check.add_argument("--agda", default="agda")
    check.add_argument("--reference-budget", type=float, default=60)
    check.add_argument("--max-output-bytes", type=int, default=MAX_OUTPUT)
    run_parser = commands.add_parser("run", help="run a complete matched panel")
    run_parser.add_argument("suite", type=Path)
    run_parser.add_argument(
        "provers", type=Path, help="JSON array of prover configurations"
    )
    run_parser.add_argument("output", type=Path)
    run_parser.add_argument("--budget", type=float, default=60.0)
    run_parser.add_argument("--environment-id", required=True)
    run_parser.add_argument("--agda", default="agda")
    run_parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    run_parser.add_argument("--order-seed", type=int, default=0)
    run_parser.add_argument("--artifacts", type=Path)
    run_parser.add_argument("--reference-budget", type=float, default=60)
    run_parser.add_argument("--max-output-bytes", type=int, default=MAX_OUTPUT)
    rating = commands.add_parser(
        "rate", help="fit matched results from any conforming evaluator"
    )
    rating.add_argument("results", nargs="+", type=Path)
    rating.add_argument("--anchor", required=True)
    rating.add_argument("--output", type=Path, required=True)
    rating.add_argument("--markdown", type=Path)
    rating.add_argument("--bootstrap", type=int, default=200)
    rating.add_argument("--seed", type=int, default=0)
    rating.add_argument("--prior-sd", type=float, default=800.0)
    rating.add_argument(
        "--domain", help="fit a separate domain rating, if its graph is connected"
    )
    demo = commands.add_parser(
        "demo", help="write explicitly simulated results and a rating report"
    )
    demo.add_argument("directory", type=Path)
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--bootstrap", type=int, default=200)
    baseline = commands.add_parser(
        "baseline", help="fixed four-term lambda baseline worker"
    )
    baseline.add_argument("source", type=Path)
    baseline.add_argument("--agda", default="agda")
    baseline.add_argument("--budget", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            save(args.output, smoke_suite(seed=args.seed, variants=args.variants))
        elif args.command == "rate":
            data = merge(
                [json.loads(p.read_text(encoding="utf-8")) for p in args.results]
            )
            if args.domain:
                data["tasks"] = [t for t in data["tasks"] if t["domain"] == args.domain]
                selected = {t["id"] for t in data["tasks"]}
                data["results"] = [r for r in data["results"] if r["task"] in selected]
                data["suite_id"] = digest([data["suite_id"], args.domain])
                data["protocol"] = dict(data["protocol"], domain=args.domain)
            report = rate(
                data,
                args.anchor,
                bootstrap=args.bootstrap,
                seed=args.seed,
                prior_sd=args.prior_sd,
            )
            save(args.output, report)
            if args.markdown:
                args.markdown.parent.mkdir(parents=True, exist_ok=True)
                args.markdown.write_text(markdown(report), encoding="utf-8")
        elif args.command == "demo":
            data = simulated(seed=args.seed)
            report = rate(
                data, "simulated-reference", bootstrap=args.bootstrap, seed=args.seed
            )
            save(args.directory / "simulated-results.json", data)
            save(args.directory / "simulated-ratings.json", report)
            (args.directory / "simulated-report.md").write_text(
                markdown(report), encoding="utf-8"
            )
        else:
            from . import runner

            if args.command == "baseline":
                if not math.isfinite(args.budget) or args.budget <= 0:
                    raise ValueError("budget must be positive and finite")
                print(
                    json.dumps(
                        runner.baseline(
                            args.source, runner.executable(args.agda), args.budget
                        )
                    )
                )
            else:
                suite = json.loads(args.suite.read_text(encoding="utf-8"))
                if args.command == "check-suite":
                    runner.validate_suite(
                        suite,
                        runner.executable(args.agda),
                        reference_budget=args.reference_budget,
                        max_output=args.max_output_bytes,
                    )
                    print(f"Checked {len(suite['tasks'])} reference proofs.")
                else:
                    if args.output.exists():
                        raise ValueError("results already exist; use a new run path")
                    provers = json.loads(args.provers.read_text(encoding="utf-8"))
                    result = runner.run(
                        suite,
                        provers,
                        agda=args.agda,
                        budget=args.budget,
                        environment_id=args.environment_id,
                        seeds=args.seeds,
                        artifacts=args.artifacts
                        or args.output.with_suffix(".artifacts"),
                        order_seed=args.order_seed,
                        reference_budget=args.reference_budget,
                        max_output=args.max_output_bytes,
                    )
                    save(args.output, result)
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RuntimeError,
        TimeoutError,
    ) as error:
        print(f"rating error: {error}", file=sys.stderr)
        return 2
    return 0
