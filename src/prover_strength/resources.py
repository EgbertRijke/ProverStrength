"""Resource-sensitive completion curves, with family-balanced paired evidence.

No proof acceptance or search lives here. Missing work is never imputed as zero.
The bounded index is a declared utility, not a fitted universal/Elo ability.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Any

from .data import digest, positive, validate
from .effort import FIELDS
from .model import quantile

PROFILE = "prover-strength.resource-profile.v1"
REPORT = "prover-strength.resource-report.v1"
METHOD = "family-balanced-log-resource-area-v1"
TIME = "elapsed_seconds"


def validate_profile(profile: object, *, wall_budget: float | None = None) -> None:
    if (
        not isinstance(profile, dict)
        or set(profile)
        not in (
            {"schema_version", "ranges"},
            {"schema_version", "ranges", "effort_accounting"},
        )
        or profile.get("schema_version") != PROFILE
    ):
        raise ValueError("invalid resource profile schema")
    ranges = profile["ranges"]
    if (
        not isinstance(ranges, dict)
        or TIME not in ranges
        or not set(ranges) <= {TIME, *FIELDS}
    ):
        raise ValueError("resource profile needs time and supported resource axes")
    for bounds in ranges.values():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("resource range must contain two bounds")
        lo, hi = (positive(x, "resource bound") for x in bounds)
        if not lo < hi:
            raise ValueError("resource bounds must strictly increase")
    if wall_budget is not None and ranges[TIME][1] > wall_budget:
        raise ValueError("resource range exceeds the observed wall allowance")
    accounting = profile.get("effort_accounting")
    if (set(ranges) & set(FIELDS) or "effort_accounting" in profile) and (
        not isinstance(accounting, str) or not accounting.strip()
    ):
        raise ValueError("effort axes require an explicit accounting identity")


def utility(cost: float | int, bounds: list[float]) -> float:
    lo, hi = bounds
    if cost <= lo:
        return 1.0
    if cost >= hi:
        return 0.0

    def log_span(lower: float, upper: float) -> float:
        # Nearby large bounds can have identical rounded logarithms.
        if upper <= 2 * lower:
            return math.log1p((upper - lower) / lower)
        return math.log(upper) - math.log(lower)

    return log_span(cost, hi) / log_span(lo, hi)


def resource_report(
    data: dict[str, Any],
    profile: dict[str, Any],
    *,
    reference: str | None = None,
    bootstrap: int = 200,
    seed: int = 0,
    retrospective: bool = False,
) -> dict[str, Any]:
    validate(data)
    validate_profile(profile, wall_budget=data["protocol"]["budget_seconds"])
    if type(bootstrap) is not int or bootstrap < 0 or type(seed) is not int:
        raise ValueError("bootstrap draws and seed must be integers; draws nonnegative")
    recorded = data["protocol"].get("resource_profile")
    if recorded is not None and recorded != profile:
        raise ValueError("resource profile differs from the pre-recorded protocol")
    if recorded is None and not retrospective:
        raise ValueError(
            "profile was not recorded before execution; use explicit retrospective analysis"
        )
    names = sorted(p["id"] for p in data["provers"])
    if reference is not None and reference not in names:
        raise ValueError("reference must identify a measured contestant")
    tasks = {t["id"]: t for t in data["tasks"]}
    families: dict[str, list[str]] = defaultdict(list)
    domains: dict[str, list[str]] = defaultdict(list)
    for task in data["tasks"]:
        families[task["family"]].append(task["id"])
    for family in sorted(families):
        domains[tasks[families[family][0]]["domain"]].append(family)
    weights = {
        task: 1
        / (
            len(domains)
            * len(domains[tasks[task]["domain"]])
            * len(families[tasks[task]["family"]])
            * len(data["seeds"])
        )
        for task in tasks
    }
    rows = {(r["prover"], r["task"], r["seed"]): r for r in data["results"]}
    slots = [(t, s) for t in sorted(tasks) for s in sorted(data["seeds"])]
    family_slots: dict[str, list[int]] = defaultdict(list)
    for index, (task, _) in enumerate(slots):
        family_slots[tasks[task]["family"]].append(index)
    axes = list(profile["ranges"])

    def cost(row: dict[str, Any], axis: str) -> float | int | None:
        if axis == TIME:
            return row[TIME]
        effort = row.get("effort")
        if effort is None or effort["accounting"] != profile.get("effort_accounting"):
            return None
        return effort[axis]

    def aggregate(values: dict[str, float]) -> float:
        return math.fsum(
            math.fsum(values[f] for f in fs) / len(fs) for fs in domains.values()
        ) / len(domains)

    scores: dict[tuple[str, str], dict[str, float]] = {}
    measurements = []
    ratings = []
    for name in names:
        selected = [rows[name, t, s] for t, s in slots]
        axis_results = {}
        for axis in axes:
            bounds = profile["ranges"][axis]
            costs = [cost(r, axis) for r in selected]
            lower = [
                utility(c, bounds)
                if r["status"] == "verified" and c is not None
                else 0.0
                for r, c in zip(selected, costs, strict=True)
            ]
            unknown_success = [
                r["status"] == "verified" and c is None
                for r, c in zip(selected, costs, strict=True)
            ]
            incomplete = any(unknown_success)
            weighted_lower = math.fsum(
                weights[t] * u for (t, _), u in zip(slots, lower, strict=True)
            )
            missing_mass = math.fsum(
                weights[t] * unknown
                for (t, _), unknown in zip(slots, unknown_success, strict=True)
            )
            family_values = {
                family: math.fsum(lower[i] for i in indices) / len(indices)
                for family, indices in family_slots.items()
            }
            scores[name, axis] = family_values
            unknown_domains = {
                tasks[t]["domain"]
                for (t, _), unknown in zip(slots, unknown_success, strict=True)
                if unknown
            }
            known = [c for c in costs if c is not None]
            events: dict[float, list[float]] = {bounds[0]: [], bounds[1]: []}
            for row, value in zip(selected, costs, strict=True):
                if (
                    row["status"] == "verified"
                    and value is not None
                    and value <= bounds[1]
                ):
                    events.setdefault(max(bounds[0], value), []).append(
                        weights[row["task"]]
                    )
            curve = []
            fraction = 0.0
            for value, mass in sorted(events.items()):
                fraction = min(1.0, math.fsum((fraction, *mass)))
                curve.append(
                    {
                        "resource": value,
                        "verified_fraction": fraction if not incomplete else None,
                        "bounds": [fraction, min(1.0, fraction + missing_mass)],
                    }
                )
            axis_results[axis] = {
                "rating": 100 * weighted_lower if not incomplete else None,
                "rating_bounds": [
                    100 * weighted_lower,
                    min(100.0, 100 * (weighted_lower + missing_mass)),
                ],
                "interval95": None,
                "rating_by_domain": {
                    domain: 100
                    * math.fsum(family_values[f] for f in members)
                    / len(members)
                    if domain not in unknown_domains
                    else None
                    for domain, members in domains.items()
                },
                "known_trials": len(known),
                "unknown_trials": len(selected) - len(known),
                "unknown_verified_trials": sum(unknown_success),
                "observed_total": sum(known),
                "total": sum(known) if len(known) == len(selected) else None,
                "curve": curve,
            }
        solved = {
            d: math.fsum(
                sum(
                    rows[name, t, s]["status"] == "verified"
                    for t in families[f]
                    for s in data["seeds"]
                )
                / (len(families[f]) * len(data["seeds"]))
                for f in fs
            )
            / len(fs)
            for d, fs in domains.items()
        }
        ratings.append(
            {
                "prover": name,
                "axes": axis_results,
                "balanced_solve_rate": math.fsum(solved.values()) / len(solved),
                "solve_rate_by_domain": solved,
                "outcomes": dict(Counter(r["status"] for r in selected)),
                "evaluator_checks": sum(r.get("evaluator_checks", 0) for r in selected)
                if all("evaluator_checks" in r for r in selected)
                else None,
            }
        )
        for row in selected:
            measurements.append(
                {
                    "prover": name,
                    "task": row["task"],
                    "seed": row["seed"],
                    "status": row["status"],
                    "costs": {axis: cost(row, axis) for axis in axes},
                    "evaluator_checks": row.get("evaluator_checks"),
                }
            )
    by_name = {r["prover"]: r for r in ratings}
    intervals_ok = bootstrap >= 100 and all(len(fs) >= 2 for fs in domains.values())
    rng = random.Random(seed)
    draws: dict[tuple[str, str], list[float]] = {key: [] for key in scores}
    for _ in range(bootstrap):
        counts = Counter(
            f
            for d in sorted(domains)
            for f in rng.choices(domains[d], k=len(domains[d]))
        )
        for key, family_scores in scores.items():
            draws[key].append(
                100
                * aggregate({f: family_scores[f] * counts[f] for f in family_scores})
            )
    for name in names:
        for axis in axes:
            result = by_name[name]["axes"][axis]
            if intervals_ok and result["rating"] is not None:
                result["interval95"] = [
                    quantile(draws[name, axis], p) for p in (0.025, 0.975)
                ]
    comparisons = []
    if reference is not None:
        for name in names:
            if name == reference:
                continue
            baseline = [rows[reference, t, s] for t, s in slots]
            candidate = [rows[name, t, s] for t, s in slots]
            counts = Counter(
                (
                    "both_verified"
                    if b["status"] == c["status"] == "verified"
                    else "candidate_only"
                    if c["status"] == "verified"
                    else "reference_only"
                    if b["status"] == "verified"
                    else "neither_verified"
                )
                for b, c in zip(baseline, candidate, strict=True)
            )
            paired_axes = {}
            for axis in axes:
                left = by_name[reference]["axes"][axis]["rating"]
                right = by_name[name]["axes"][axis]["rating"]
                paired = [
                    (t, cost(b, axis), cost(c, axis))
                    for (t, _), b, c in zip(slots, baseline, candidate, strict=True)
                    if b["status"] == c["status"] == "verified"
                ]
                usable = [
                    (weights[t], math.log(b) - math.log(c))
                    for t, b, c in paired
                    if b is not None and c is not None and b > 0 and c > 0
                ]
                log_factor = (
                    math.fsum(w * ratio for w, ratio in usable)
                    / math.fsum(w for w, _ in usable)
                    if usable
                    else None
                )
                factor = (
                    math.exp(log_factor)
                    if log_factor is not None and abs(log_factor) < 709
                    else None
                )
                differences = [
                    c - b
                    for b, c in zip(
                        draws[reference, axis], draws[name, axis], strict=True
                    )
                ]
                paired_axes[axis] = {
                    "rating_difference": right - left
                    if left is not None and right is not None
                    else None,
                    "difference_interval95": [
                        quantile(differences, p) for p in (0.025, 0.975)
                    ]
                    if intervals_ok and left is not None and right is not None
                    else None,
                    "common_verified_trials": len(paired),
                    "known_positive_common_trials": len(usable),
                    "reference_over_candidate_cost": factor,
                    "log_reference_over_candidate_cost": log_factor,
                }
            comparisons.append(
                {
                    "reference": reference,
                    "candidate": name,
                    "outcomes": dict(counts),
                    "axes": paired_axes,
                }
            )
    warnings = []
    if data["protocol"].get("synthetic"):
        warnings.append("Synthetic observations; not measured prover performance.")
    if len(families) < 30 or any(len(fs) < 5 for fs in domains.values()):
        warnings.append("Small family sample; provisional index, not general strength.")
    if not intervals_ok:
        warnings.append(
            "Intervals require 100 draws and at least two families per domain."
        )
    if recorded is None:
        warnings.append(
            "Retrospective resource profile; not a preregistered measurement."
        )
    if any(r["axes"][a]["unknown_trials"] for r in ratings for a in axes):
        warnings.append(
            "Some counters are unknown or have incompatible accounting; inspect coverage and bounds."
        )
    return {
        "schema_version": REPORT,
        "method": METHOD,
        "primary_axis": TIME,
        "profile": profile,
        "profile_recorded_before_run": recorded is not None,
        "edition_id": digest(
            {
                "method": METHOD,
                "suite_id": data["suite_id"],
                "protocol": data["protocol"],
                "profile": profile,
            }
        ),
        "input_sha256": digest(data),
        "suite_id": data["suite_id"],
        "protocol": data["protocol"],
        "family_count": len(families),
        "bootstrap": {
            "draws": bootstrap,
            "seed": seed,
            "unit": "family within domain",
            "intervals_available": intervals_ok,
        },
        "ratings": ratings,
        "comparisons": comparisons,
        "measurements": measurements,
        "warnings": warnings,
    }


def markdown(report: dict[str, Any]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    def number(value: float | None) -> str:
        return "unknown" if value is None else f"{value:.3f}"

    lines = [
        "# Resource-sensitive completion",
        "",
        "Higher indices mean earlier verified completion over the declared logarithmic resource ranges (0–100), not Elo. Resource axes are separate.",
        "",
        "| Prover | Resource | Index | 95% family interval | Known trials | Total spent |",
        "| --- | --- | ---: | --- | ---: | ---: |",
    ]
    for row in report["ratings"]:
        for axis, values in row["axes"].items():
            interval = values["interval95"]
            lines.append(
                f"| {cell(row['prover'])} | {axis} | {number(values['rating'])} | {number(interval[0]) + '–' + number(interval[1]) if interval else 'unavailable'} | {values['known_trials']}/{values['known_trials'] + values['unknown_trials']} | {number(values['total'])} |"
            )
    for pair in report["comparisons"]:
        lines.extend(
            [
                "",
                f"## {cell(pair['candidate'])} versus {cell(pair['reference'])}",
                "",
                f"Completion outcomes: `{pair['outcomes']}`.",
                "",
                "| Resource | Index difference | Common-success cost factor | Known positive pairs |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for axis, values in pair["axes"].items():
            lines.append(
                f"| {axis} | {number(values['rating_difference'])} | {number(values['reference_over_candidate_cost'])} | {values['known_positive_common_trials']}/{values['common_verified_trials']} |"
            )
    lines.extend(
        [
            "",
            "Cost factors greater than 1 favor the candidate. Common-success factors are conditional diagnostics; unsuccessful trials remain in the indices and completion outcomes.",
            "",
        ]
    )
    lines.extend("- " + message for message in report["warnings"])
    return "\n".join(lines) + "\n"
