"""Strict, prover-neutral evaluation records. No compiler imports here."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

SCHEMA = "portable-prover-rating.results.v1"
STATUSES = {
    "verified",
    "unsolved",
    "timeout",
    "resource-exhausted",
    "invalid",
    "crash",
    "unsupported",
}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)


def identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def validate(data: dict[str, Any]) -> None:
    """Require a complete, matched panel, including unsuccessful attempts."""
    if data.get("schema_version") != SCHEMA:
        raise ValueError("unsupported results schema")
    identifier(data["suite_id"], "suite_id")
    protocol = data["protocol"]
    for field in ("track", "environment_id", "checker_id", "enforcement"):
        identifier(protocol[field], field)
    positive(protocol["budget_seconds"], "budget_seconds")
    seeds = data["seeds"]
    if (
        not seeds
        or any(type(s) is not int for s in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("seeds must be distinct integers")
    tasks: dict[str, Any] = {}
    families: dict[str, str] = {}
    fingerprint_families: dict[str, str] = {}
    for task in data["tasks"]:
        name = identifier(task["id"], "task id")
        domain = identifier(task["domain"], "domain")
        family = identifier(task["family"], "family")
        fingerprint = identifier(task["sha256"], "task sha256")
        if name in tasks:
            raise ValueError(f"duplicate task: {name}")
        if family in families and families[family] != domain:
            raise ValueError("a family cannot straddle domains")
        if (
            fingerprint in fingerprint_families
            and fingerprint_families[fingerprint] != family
        ):
            raise ValueError(
                "identical task fingerprints cannot be counted as different families"
            )
        fingerprint_families[fingerprint] = family
        families[family] = domain
        tasks[name] = task
    provers: set[str] = set()
    for prover in data["provers"]:
        name = identifier(prover["id"], "prover id")
        identifier(prover["revision"], "prover revision")
        if name in provers:
            raise ValueError(f"duplicate prover: {name}")
        provers.add(name)
    if not tasks or not provers:
        raise ValueError("tasks and provers must be nonempty")
    seen: set[tuple[str, str, int]] = set()
    for row in data["results"]:
        key = row["prover"], row["task"], row["seed"]
        if key[0] not in provers or key[1] not in tasks or key[2] not in seeds:
            raise ValueError(f"unexpected observation: {key}")
        if type(key[2]) is not int or key in seen:
            raise ValueError(f"duplicate or malformed observation: {key}")
        seen.add(key)
        if row["status"] not in STATUSES:
            raise ValueError(
                f"unscored status: {row['status']}; resolve harness errors first"
            )
        elapsed = row["elapsed_seconds"]
        if (
            type(elapsed) not in (float, int)
            or not math.isfinite(elapsed)
            or elapsed < 0
        ):
            raise ValueError("elapsed_seconds must be finite and nonnegative")
        if row["status"] == "verified":
            if row.get("checker_accepted") is not True or not row.get(
                "artifact_sha256"
            ):
                raise ValueError("verified outcome lacks checker evidence")
            if elapsed > protocol["budget_seconds"]:
                raise ValueError("verified outcome exceeded the budget")
    if len(seen) != len(provers) * len(tasks) * len(seeds):
        raise ValueError(
            "incomplete panel: record every assigned prover/task/seed, including failures"
        )


def merge(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge separately executed contestants, never mismatched tracks or budgets."""
    if not bundles:
        raise ValueError("no result files")
    result = dict(bundles[0], provers=[], results=[])
    for bundle in bundles:
        validate(bundle)
        for key in ("schema_version", "suite_id", "protocol", "seeds", "tasks"):
            if bundle[key] != result[key]:
                raise ValueError(f"cannot combine different {key}")
        result["provers"].extend(bundle["provers"])
        result["results"].extend(bundle["results"])
    validate(result)
    return result
