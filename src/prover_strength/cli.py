"""Command line for independent proof evaluation, ratings, and history."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .data import digest, merge
from .model import rate
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prover-strength")
    commands = parser.add_subparsers(dest="command", required=True)
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
    run_parser.add_argument(
        "--resource-profile",
        type=Path,
        help="freeze resource-sensitive measurement ranges before execution",
    )
    resource = commands.add_parser(
        "resource-rate",
        help="measure verified completion time and effort, including common successes",
    )
    resource.add_argument("results", nargs="+", type=Path)
    resource.add_argument("--profile", type=Path, required=True)
    resource.add_argument("--reference")
    resource.add_argument("--output", type=Path, required=True)
    resource.add_argument("--markdown", type=Path)
    resource.add_argument("--bootstrap", type=int, default=200)
    resource.add_argument("--seed", type=int, default=0)
    resource.add_argument(
        "--retrospective",
        action="store_true",
        help="explicitly permit old observations without a pre-recorded resource profile",
    )
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
    archive = commands.add_parser(
        "record", help="archive a completed commit observation"
    )
    archive.add_argument("run", type=Path)
    archive.add_argument("--history", type=Path, default=Path("history"))
    chart = commands.add_parser(
        "serve-history", help="serve the live local commit chart"
    )
    chart.add_argument("--history", type=Path, default=Path("history"))
    chart.add_argument("--port", type=int, default=8765)
    chart.add_argument("--participants", type=Path, help="stable participant registry")
    static = commands.add_parser("export-history", help="export a static public chart")
    static.add_argument("destination", type=Path)
    static.add_argument("--history", type=Path, required=True)
    static.add_argument("--participants", type=Path, help="stable participant registry")
    pending = commands.add_parser(
        "measure-pending", help="measure a bounded batch of new commits"
    )
    pending.add_argument("campaign", type=Path)
    pending.add_argument("--product", type=Path, required=True)
    pending.add_argument("--evaluator", type=Path, required=True)
    pending.add_argument("--queue", type=Path, required=True)
    pending.add_argument("--history", type=Path, required=True)
    pending.add_argument("--tip", default="HEAD")
    pending.add_argument("--limit", type=int, default=2)
    pending.add_argument("--agda", default="agda")
    pending.add_argument("--environment-id", required=True)
    pending.add_argument("--network-policy", default="external-supervisor-unspecified")
    pending.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "resource-rate":
            from .resources import markdown as resource_markdown
            from .resources import resource_report

            data = merge(
                [json.loads(p.read_text(encoding="utf-8")) for p in args.results]
            )
            report = resource_report(
                data,
                json.loads(args.profile.read_text(encoding="utf-8")),
                reference=args.reference,
                bootstrap=args.bootstrap,
                seed=args.seed,
                retrospective=args.retrospective,
            )
            save(args.output, report)
            if args.markdown:
                args.markdown.parent.mkdir(parents=True, exist_ok=True)
                args.markdown.write_text(resource_markdown(report), encoding="utf-8")
        elif args.command == "measure-pending":
            from .commits import measure_pending

            batch = measure_pending(
                args.product,
                args.evaluator,
                args.queue,
                campaign=json.loads(args.campaign.read_text(encoding="utf-8")),
                tip=args.tip,
                limit=args.limit,
                agda=args.agda,
                history=args.history,
                environment_id=args.environment_id,
                network_policy=args.network_policy,
            )
            save(args.output, batch)
            print(json.dumps(batch, ensure_ascii=False))
            return 2 if batch["unresolved"] else 0
        elif args.command == "export-history":
            from .history import export

            export(args.history, args.destination, participants=args.participants)
        elif args.command == "record":
            from .history import record

            print(record(args.run, args.history))
        elif args.command == "serve-history":
            from .history import serve

            serve(args.history, args.port, participants=args.participants)
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
        else:
            from . import runner

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
                    artifacts=args.artifacts or args.output.with_suffix(".artifacts"),
                    order_seed=args.order_seed,
                    reference_budget=args.reference_budget,
                    max_output=args.max_output_bytes,
                    resource_profile=json.loads(
                        args.resource_profile.read_text(encoding="utf-8")
                    )
                    if args.resource_profile
                    else None,
                )
                save(args.output, result)
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RuntimeError,
        TimeoutError,
        subprocess.SubprocessError,
    ) as error:
        print(f"rating error: {error}", file=sys.stderr)
        return 2
    return 0
