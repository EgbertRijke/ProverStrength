"""Versioned optional work counters, separate from proof acceptance."""

from typing import Any

SCHEMA = "prover-strength.effort.v1"
AGDAPROVER = "agdaprover.p0.v1-self-reported"
FIELDS = ("actions_expanded", "verifier_calls")


def validate_effort(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "accounting",
        *FIELDS,
    }:
        raise ValueError("invalid effort record")
    if value["schema_version"] != SCHEMA:
        raise ValueError("unsupported effort schema")
    if not isinstance(value["accounting"], str) or not value["accounting"].strip():
        raise ValueError("effort needs an accounting identity")
    for field in FIELDS:
        count = value[field]
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError("effort counts must be nonnegative integers or unknown")


def reported_effort(payload: dict[str, Any], adapter: str) -> dict[str, Any] | None:
    value: Any
    if adapter == "agdaprover":
        if payload.get("schema_version") != "agdaprover.p0.v1":
            return None
        cost = payload.get("cost")
        value = {
            "schema_version": SCHEMA,
            "accounting": AGDAPROVER,
            "actions_expanded": cost.get("actions_expanded")
            if isinstance(cost, dict)
            else None,
            "verifier_calls": payload.get("verifier_calls"),
        }
        # Invalid optional counters cannot invalidate an otherwise sound proof.
        for field in FIELDS:
            if type(value[field]) is not int or value[field] < 0:
                value[field] = None
    else:
        value = payload.get("effort")
    if value is None:
        return None
    try:
        validate_effort(value)
    except ValueError:
        return None
    return dict(value)
