"""Versioned, data-only measurement campaigns; no bundled test banks or provers."""

import re
from pathlib import PurePosixPath
from typing import Any

from .data import identifier, positive


def validate_campaign(value: dict[str, Any]) -> None:
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "prover-strength.campaign.v1"
    ):
        raise ValueError("unsupported measurement campaign")
    identifier(value["id"], "campaign id")
    for key in ("evaluator_commit", "first_commit"):
        if not isinstance(value[key], str) or not re.fullmatch(
            r"[a-f0-9]{40}", value[key]
        ):
            raise ValueError(f"{key} must pin a full Git commit")
    suite = value["suite"]
    if not re.fullmatch(r"[a-f0-9]{64}", suite["sha256"]):
        raise ValueError("suite must pin a SHA-256 digest")
    path = PurePosixPath(suite["path"])
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("suite path must remain inside the evaluator snapshot")
    for key in ("reference", "participant"):
        entry = value[key]
        identifier(entry["id"], key + " id")
        if entry["adapter"] not in ("candidate-json", "agdaprover"):
            raise ValueError("unsupported contestant adapter")
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", entry["module"]):
            raise ValueError("contestant module must be a Python module name")
        if not isinstance(entry["arguments"], list) or not all(
            isinstance(x, str) and "\0" not in x for x in entry["arguments"]
        ):
            raise ValueError("contestant arguments must be a string array")
    profile = value["profile"]
    positive(profile["budget_seconds"], "budget")
    positive(profile["reference_check_budget_seconds"], "reference budget")
    if type(profile["max_output_bytes"]) is not int or profile["max_output_bytes"] < 1:
        raise ValueError("output budget must be a positive integer")
    seeds = profile["seeds"]
    if (
        not isinstance(seeds, list)
        or not seeds
        or any(type(s) is not int for s in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("seeds must be distinct integers")
    if type(profile["order_seed"]) is not int:
        raise ValueError("order seed must be an integer")
