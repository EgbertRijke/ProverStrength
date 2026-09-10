"""Untrusted candidate decoding; no imports from a contestant implementation."""

from typing import Any


def agdaprover_candidate(source: str, patch: dict[str, Any]) -> str:
    """Decode the public v1 edit as a proposal, not as an accepted product patch.

    Product-only step/lineage diagnostics confer no authority here. The evaluator
    separately preserves the immutable prefix and freshly checks the whole source.
    Offsets in this contract are one-based Unicode code points, end-exclusive.
    """
    if patch.get("schema_version") != "agdaprover.reconstruction.p0.v1":
        raise ValueError("unsupported AgdaProver reconstruction schema")
    span = patch.get("source_range")
    if not (
        isinstance(span, list) and len(span) == 2 and all(type(x) is int for x in span)
    ):
        raise ValueError("invalid reconstruction range")
    start, end = span
    if not 1 <= start < end <= len(source) + 1:
        raise ValueError("reconstruction range is outside source")
    original, replacement = patch.get("original"), patch.get("replacement")
    if not isinstance(original, str) or not isinstance(replacement, str):
        raise ValueError("reconstruction text must be strings")
    if source[start - 1 : end - 1] != original:
        raise ValueError("reconstruction original does not match source")
    return source[: start - 1] + replacement + source[end - 1 :]
