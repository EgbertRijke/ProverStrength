"""Recorded measurements stay complete, stable, and separate by protocol."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from prover_strength.cli import simulated
from prover_strength.data import digest
from prover_strength.history import observation, points, record
from prover_strength.model import rate
from prover_strength.runner import file_sha256


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(root):
    root.mkdir()
    result = simulated(families_per_domain=5)
    result["provers"] = [
        p
        | {
            "revision": "product" if p["id"] == "simulated-strong" else "baseline",
            "argv": [
                "python",
                str(
                    root / "product/src"
                    if p["id"] == "simulated-strong"
                    else root / "evaluator/src"
                ),
            ],
            "executable_sha256": "python-hash",
        }
        for p in result["provers"]
    ]
    report = rate(result, "simulated-reference", bootstrap=0)
    write(root / "results.json", result)
    write(root / "ratings.json", report)
    write(
        root / "observation.json",
        {
            "schema_version": "prover-strength.commit-observation.v1",
            "product_commit": "product",
            "evaluator_commit": "evaluator",
            "evaluator_tree": "tree",
            "profile": {"ranker": "symbolic", "search": "deep"},
            "environment": {"id": "test"},
            "suite_id": result["suite_id"],
        },
    )
    write(
        root / "completed.json",
        {
            "source_integrity": "unchanged",
            "finished_at": "2026-09-10T00:00:00Z",
            "results_sha256": file_sha256(str(root / "results.json")),
            "ratings_sha256": file_sha256(str(root / "ratings.json")),
        },
    )
    (root / "report.md").write_text("# Simulated test fixture\n")
    for row in result["results"]:
        name = digest([row["prover"], row["task"], row["seed"]])[:24]
        write(
            root / "artifacts" / (name + ".json"),
            {
                "stdout": json.dumps(
                    {"cost": {"actions_expanded": 10}, "verifier_calls": 5}
                )
            },
        )
    return result


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / "run"
        self.result = fixture(self.run)

    def test_record_and_repeat_are_idempotent(self):
        first = record(self.run, self.root / "history")
        self.assertEqual(record(self.run, self.root / "history"), first)
        stored = points(self.root / "history")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["product_commit"], "product")
        self.assertEqual(stored[0]["effort"]["actions_expanded"]["total"], 600)
        self.assertGreater(stored[0]["effort"]["proofs_per_1000_actions"], 0)

    def test_failed_trial_effort_is_counted_and_unknown_is_not_zero(self):
        failed = next(
            r
            for r in self.result["results"]
            if r["prover"] == "simulated-strong" and r["status"] != "verified"
        )
        name = digest([failed["prover"], failed["task"], failed["seed"]])[:24]
        write(self.run / "artifacts" / (name + ".json"), {"error": "deadline"})
        measured = observation(self.run)["effort"]
        self.assertEqual(measured["actions_expanded"]["known_trials"], 59)
        self.assertEqual(measured["actions_expanded"]["unknown_trials"], 1)
        self.assertIsNone(measured["actions_expanded"]["total"])
        self.assertIsNone(measured["proofs_per_1000_actions"])

    def test_changed_results_are_rejected(self):
        write(self.run / "results.json", {})
        with self.assertRaisesRegex(ValueError, "changed results"):
            observation(self.run)

    def test_source_integrity_failure_is_rejected(self):
        path = self.run / "completed.json"
        receipt = json.loads(path.read_text())
        write(path, receipt | {"source_integrity": "changed"})
        with self.assertRaisesRegex(ValueError, "source integrity"):
            observation(self.run)

    def test_modified_existing_point_is_not_overwritten(self):
        destination = record(self.run, self.root / "history")
        write(destination / "point.json", {})
        with self.assertRaisesRegex(ValueError, "modified evidence"):
            record(self.run, self.root / "history")

    def test_paths_do_not_change_series_but_protocols_do(self):
        other = self.root / "other"
        fixture(other)
        initial = observation(self.run)
        self.assertEqual(observation(other)["series_id"], initial["series_id"])
        path = other / "observation.json"
        metadata = json.loads(path.read_text())
        metadata["profile"]["ranker"] = "nnue"
        write(path, metadata)
        self.assertNotEqual(observation(other)["series_id"], initial["series_id"])

    def test_new_product_commit_keeps_the_series(self):
        initial = observation(self.run)
        path = self.run / "results.json"
        result = json.loads(path.read_text())
        for p in result["provers"]:
            if p["revision"] == "product":
                p["revision"] = "new-product"
        write(path, result)
        report = rate(result, "simulated-reference", bootstrap=0)
        write(self.run / "ratings.json", report)
        path = self.run / "observation.json"
        write(path, json.loads(path.read_text()) | {"product_commit": "new-product"})
        path = self.run / "completed.json"
        write(
            path,
            json.loads(path.read_text())
            | {
                "results_sha256": file_sha256(str(self.run / "results.json")),
                "ratings_sha256": file_sha256(str(self.run / "ratings.json")),
            },
        )
        later = observation(self.run)
        self.assertNotEqual(later["id"], initial["id"])
        self.assertEqual(later["series_id"], initial["series_id"])

    def test_modified_archived_results_are_not_silently_reused(self):
        destination = record(self.run, self.root / "history")
        write(destination / "results.json", {})
        with self.assertRaisesRegex(ValueError, "modified archived evidence"):
            record(self.run, self.root / "history")

    def test_changed_proof_is_rejected(self):
        result = self.result
        result["protocol"].pop("synthetic")
        report = rate(result, "simulated-reference", bootstrap=0)
        write(self.run / "results.json", result)
        write(self.run / "ratings.json", report)
        for row in result["results"]:
            if row["status"] == "verified":
                name = digest([row["prover"], row["task"], row["seed"]])[:24]
                (self.run / "artifacts" / (name + ".agda")).write_text("changed proof")
        path = self.run / "completed.json"
        write(
            path,
            json.loads(path.read_text())
            | {
                "results_sha256": file_sha256(str(self.run / "results.json")),
                "ratings_sha256": file_sha256(str(self.run / "ratings.json")),
            },
        )
        with self.assertRaisesRegex(ValueError, "changed independently checked proof"):
            observation(self.run)
