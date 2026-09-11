"""Task framing and fingerprints shared by evaluator adapters."""

from typing import Any

from .data import digest

HEADER = "{-# OPTIONS --without-K --exact-split #-}\nmodule Task where\n\n"


def suite_metadata(suite: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": t["id"],
            "domain": t["domain"],
            "family": t["family"],
            "sha256": digest(
                {
                    "prefix": t["prefix"],
                    "starter": t["starter"],
                    **(
                        {"context_id": t["context_id"], "entrypoint": t["entrypoint"]}
                        if "context_id" in t
                        else {}
                    ),
                }
            ),
        }
        for t in suite["tasks"]
    ]
