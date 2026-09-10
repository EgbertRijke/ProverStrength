"""Family-balanced conditional Rasch / Bradley--Terry composite likelihood.

Scores use natural logits internally and 400/log(10) points per logit.
Only discordant paired outcomes enter the fit. Uncertainty resamples entire
families, preserving dependence among tasks, seeds, and all induced pairs.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Any

from .data import digest, positive, validate

SCALE = 400.0 / math.log(10.0)
Edge = tuple[int, int, float, float]  # first, second, first wins, second wins


def logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def components(n: int, edges: list[Edge], *, directed: bool = False) -> list[list[int]]:
    adjacency: list[set[int]] = [set() for _ in range(n)]
    for a, b, wins, losses in edges:
        if wins or (losses and not directed):
            adjacency[a].add(b)
        if losses or (wins and not directed):
            adjacency[b].add(a)
    reachable: list[set[int]] = []
    for start in range(n):
        found = {start}
        todo = [start]
        while todo:
            for target in adjacency[todo.pop()] - found:
                found.add(target)
                todo.append(target)
        reachable.append(found)
    remaining = set(range(n))
    groups = []
    while remaining:
        start = min(remaining)
        group = sorted(
            i for i in remaining if i in reachable[start] and start in reachable[i]
        )
        groups.append(group)
        remaining.difference_update(group)
    return groups


def fit(n: int, edges: list[Edge], anchor: int, prior_sd: float) -> list[float]:
    """Strictly convex penalized fit; anchor fixed at zero, no order-dependent Elo updates."""
    ratio = SCALE / positive(prior_sd, "prior_sd")
    precision = ratio * ratio
    if not math.isfinite(precision) or precision <= 0:
        raise ValueError("prior_sd is outside the numerically supported range")
    neighbours: list[list[tuple[int, float, float]]] = [[] for _ in range(n)]
    for a, b, wins, losses in edges:
        neighbours[a].append((b, wins, wins + losses))
        neighbours[b].append((a, losses, wins + losses))
    theta = [0.0] * n
    for _ in range(20000):
        for i in range(n):
            if i == anchor:
                continue
            # Exact one-coordinate minimization, bracketed because Newton alone
            # can overshoot on completely separated observations.
            lo, hi = -1.0, 1.0

            def gradient(x: float, i: int = i) -> float:
                return precision * x + sum(
                    total * logistic(x - theta[j]) - wins
                    for j, wins, total in neighbours[i]
                )

            while gradient(lo) > 0:
                lo *= 2
            while gradient(hi) < 0:
                hi *= 2
            for _inner in range(42):
                mid = (lo + hi) / 2
                if gradient(mid) > 0:
                    hi = mid
                else:
                    lo = mid
            theta[i] = (lo + hi) / 2
        residual = max(
            (
                abs(
                    precision * theta[i]
                    + sum(
                        total * logistic(theta[i] - theta[j]) - wins
                        for j, wins, total in neighbours[i]
                    )
                )
                for i in range(n)
                if i != anchor
            ),
            default=0,
        )
        if residual < 1e-8:
            return theta
    raise ValueError("rating optimizer did not converge")


def quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    x = (len(ordered) - 1) * p
    i = int(x)
    return ordered[i] + (x - i) * (ordered[min(i + 1, len(ordered) - 1)] - ordered[i])


def rate(
    data: dict[str, Any],
    anchor: str,
    *,
    bootstrap: int = 200,
    seed: int = 0,
    prior_sd: float = 800.0,
) -> dict[str, Any]:
    validate(data)
    positive(prior_sd, "prior_sd")
    if type(bootstrap) is not int or bootstrap < 0:
        raise ValueError("bootstrap must be a nonnegative integer")
    names = sorted(p["id"] for p in data["provers"])
    if len(names) < 2 or anchor not in names:
        raise ValueError("at least two provers and a present anchor are required")
    n, anchor_index = len(names), names.index(anchor)
    task_map = {t["id"]: t for t in data["tasks"]}
    by_family: dict[str, list[str]] = defaultdict(list)
    by_domain: dict[str, list[str]] = defaultdict(list)
    for task in data["tasks"]:
        by_family[task["family"]].append(task["id"])
    for family, tasks in sorted(by_family.items()):
        by_domain[task_map[tasks[0]]["domain"]].append(family)
    outcomes = {
        (r["prover"], r["task"], r["seed"]): int(r["status"] == "verified")
        for r in data["results"]
    }
    family_edges: dict[str, list[Edge]] = {}
    domain_solved: dict[str, list[float]] = {d: [0.0] * n for d in by_domain}
    pair_counts: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    total_families = len(by_family)
    for family, tasks in sorted(by_family.items()):
        domain = task_map[tasks[0]]["domain"]
        cells = len(tasks) * len(data["seeds"])
        # Each domain gets F/D total mass; each family shares its domain equally.
        family_weight = total_families / (len(by_domain) * len(by_domain[domain]))
        wins_by_pair: dict[tuple[int, int], list[float]] = defaultdict(
            lambda: [0.0, 0.0]
        )
        family_solved = [0] * n
        for task in sorted(tasks):
            for trial in sorted(data["seeds"]):
                solved = [outcomes[name, task, trial] for name in names]
                for a in range(n):
                    family_solved[a] += solved[a]
                    for b in range(a + 1, n):
                        label = (
                            "both_solved" if solved[a] and solved[b] else "both_failed"
                        )
                        if solved[a] != solved[b]:
                            label = "first_only" if solved[a] else "second_only"
                            wins_by_pair[a, b][0 if solved[a] else 1] += 1
                        pair_counts[a, b][label] += 1
        for a in range(n):
            domain_solved[domain][a] += family_solved[a] / (
                cells * len(by_domain[domain])
            )
        family_edges[family] = [
            (
                a,
                b,
                (w / cells) * family_weight / (n - 1),
                (losses / cells) * family_weight / (n - 1),
            )
            for (a, b), (w, losses) in sorted(wins_by_pair.items())
        ]

    def aggregate(counts: dict[str, int]) -> list[Edge]:
        pairs: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for family, count in sorted(counts.items()):
            for a, b, w, losses in family_edges[family]:
                pairs[a, b][0] += w * count
                pairs[a, b][1] += losses * count
        return [
            (a, b, w, losses)
            for (a, b), (w, losses) in sorted(pairs.items())
            if w + losses > 0
        ]

    edges = aggregate(dict.fromkeys(by_family, 1))
    groups = components(n, edges)
    if len(groups) != 1:
        raise ValueError(
            "no identifiable common rating: disconnected discordance groups "
            + repr([[names[i] for i in group] for group in groups])
        )
    theta = fit(n, edges, anchor_index, prior_sd)
    separated = len(components(n, edges, directed=True)) != 1
    rng = random.Random(seed)
    draws: list[list[float]] = []
    disconnected_draws = 0
    for _ in range(bootstrap):
        counts: Counter[str] = Counter()
        for domain in sorted(by_domain):
            families = by_domain[domain]
            counts.update(rng.choices(families, k=len(families)))
        sampled = aggregate(counts)
        disconnected_draws += len(components(n, sampled)) != 1
        draws.append(fit(n, sampled, anchor_index, prior_sd))
    # Do not silently discard disconnected resamples and narrow the interval.
    intervals_ok = bootstrap >= 100 and disconnected_draws == 0 and not separated
    warnings = []
    if total_families < 30 or any(len(f) < 5 for f in by_domain.values()):
        warnings.append(
            "Small family sample: ratings are provisional; renamed tasks are not new families."
        )
    if separated:
        warnings.append(
            "Complete/quasi separation: finite ratings depend on the prior; intervals withheld."
        )
    if bootstrap < 100:
        warnings.append("Fewer than 100 bootstrap draws: intervals withheld.")
    if disconnected_draws:
        warnings.append(
            "Some family resamples disconnect the comparison graph: intervals withheld."
        )
    if data["protocol"].get("synthetic"):
        warnings.append(
            "SIMULATED outcomes: these are not measurements of real provers."
        )
    ratings = []
    for i, name in enumerate(names):
        values = [1500 + SCALE * draw[i] for draw in draws]
        ratings.append(
            {
                "prover": name,
                "rating": round(1500 + SCALE * theta[i], 2),
                "interval95": [round(quantile(values, p), 2) for p in (0.025, 0.975)]
                if intervals_ok
                else None,
                "anchor": name == anchor,
                "balanced_solve_rate": sum(v[i] for v in domain_solved.values())
                / len(by_domain),
                "solve_rate_by_domain": {
                    d: v[i] for d, v in sorted(domain_solved.items())
                },
            }
        )
    comparisons = []
    for (a, b), counts in sorted(pair_counts.items()):
        values = [SCALE * (draw[a] - draw[b]) for draw in draws]
        comparisons.append(
            {
                "first": names[a],
                "second": names[b],
                "counts": dict(counts),
                "difference": round(SCALE * (theta[a] - theta[b]), 2),
                "difference_interval95": [
                    round(quantile(values, p), 2) for p in (0.025, 0.975)
                ]
                if intervals_ok
                else None,
                "model_first_only_given_discordance": logistic(theta[a] - theta[b]),
            }
        )
    sensitivity = fit(n, edges, anchor_index, prior_sd * 2)
    residuals = [
        {
            "first": names[a],
            "second": names[b],
            "observed_first_only_fraction": w / (w + losses),
            "predicted_first_only_fraction": logistic(theta[a] - theta[b]),
            "effective_discordance_weight": w + losses,
        }
        for a, b, w, losses in edges
    ]
    return {
        "schema_version": "portable-prover-rating.report.v1",
        "method": "conditional-rasch-bt-v1",
        "scale_id": digest(
            {
                "method": "conditional-rasch-bt-v1",
                "suite_id": data["suite_id"],
                "protocol": data["protocol"],
                "prior_sd_points": prior_sd,
                "anchor": next(p for p in data["provers"] if p["id"] == anchor),
            }
        ),
        "suite_id": data["suite_id"],
        "protocol": data["protocol"],
        "input_sha256": digest(data),
        "anchor": next(p for p in data["provers"] if p["id"] == anchor),
        "prior_sd_points": prior_sd,
        "family_count": total_families,
        "bootstrap": {
            "draws": bootstrap,
            "seed": seed,
            "disconnected_draws": disconnected_draws,
            "unit": "family within domain",
            "intervals_available": intervals_ok,
        },
        "separation": separated,
        "warnings": warnings,
        "ratings": sorted(ratings, key=lambda r: (-r["rating"], r["prover"])),
        "comparisons": comparisons,
        "pairwise_fit": residuals,
        "prior_sensitivity_max_shift_points": max(
            abs(SCALE * (x - y)) for x, y in zip(theta, sensitivity, strict=True)
        ),
    }
