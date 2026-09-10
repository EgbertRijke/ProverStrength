"""Statistical identities, sampling units, malformed records, and live checking."""

from __future__ import annotations

import copy
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from prover_strength.benchmark import smoke_suite
from prover_strength.cli import main, simulated
from prover_strength.data import SCHEMA, merge, validate
from prover_strength.model import SCALE, components, fit, logistic, rate
from prover_strength.runner import (
    HarnessError,
    candidate_from_result,
    check_source,
    process,
    run,
    validate_candidate,
    validate_suite,
)

AGDA = os.environ.get("PPR_TEST_AGDA")
PROVER = os.environ.get("PPR_TEST_PROVER")


def panel(patterns: list[tuple[int, int]]) -> dict:
    tasks, rows = [], []
    for i, outcomes in enumerate(patterns):
        tasks.append(
            {"id": str(i), "domain": "logic", "family": str(i), "sha256": str(i)}
        )
        for name, outcome in zip(("A", "B"), outcomes, strict=True):
            rows.append(
                {
                    "prover": name,
                    "task": str(i),
                    "seed": 0,
                    "status": "verified" if outcome else "timeout",
                    "elapsed_seconds": 1.0,
                    "checker_accepted": bool(outcome),
                    "artifact_sha256": "test-fixture" if outcome else None,
                }
            )
    return {
        "schema_version": SCHEMA,
        "suite_id": "test-fixture",
        "tasks": tasks,
        "provers": [{"id": name, "revision": "v1"} for name in ("A", "B")],
        "protocol": {
            "track": "test",
            "budget_seconds": 10,
            "environment_id": "test",
            "checker_id": "test",
            "enforcement": "test",
        },
        "seeds": [0],
        "results": rows,
    }


class RatingMathTests(unittest.TestCase):
    def test_elo_scale_and_task_difficulty_cancellation(self) -> None:
        self.assertAlmostEqual(logistic(400 / SCALE), 10 / 11)
        for difficulty in (-10, -3, 0, 4, 10):
            pa, pb = logistic(1.4 - difficulty), logistic(-0.7 - difficulty)
            conditional = pa * (1 - pb) / (pa * (1 - pb) + pb * (1 - pa))
            self.assertAlmostEqual(conditional, logistic(2.1), places=10)

    def test_known_unregularized_two_player_solution(self) -> None:
        theta = fit(2, [(0, 1, 30, 10)], 1, 1e8)
        self.assertAlmostEqual(theta[0], math.log(3), places=7)
        self.assertEqual(theta[1], 0)

    def test_extreme_logistic_is_finite(self) -> None:
        self.assertEqual(logistic(-10000), 0)
        self.assertEqual(logistic(10000), 1)

    def test_joint_fit_recovers_known_abilities(self) -> None:
        expected = [0.0, 1.0, -0.5, 2.0]
        edges = [
            (
                a,
                b,
                1000 * logistic(expected[a] - expected[b]),
                1000 * logistic(expected[b] - expected[a]),
            )
            for a in range(4)
            for b in range(a + 1, 4)
        ]
        actual = fit(4, edges, 0, 1e8)
        for a, b in zip(actual, expected, strict=True):
            self.assertAlmostEqual(a, b, places=7)

    def test_perfect_records_are_finite_and_flagged(self) -> None:
        report = rate(panel([(1, 0)] * 10), "B", bootstrap=100)
        self.assertTrue(report["separation"])
        self.assertFalse(report["bootstrap"]["intervals_available"])
        self.assertGreater(report["ratings"][0]["rating"], 1500)
        self.assertTrue(math.isfinite(report["ratings"][0]["rating"]))

    def test_common_success_and_failure_do_not_become_draws(self) -> None:
        base = rate(panel([(1, 0)] * 3 + [(0, 1)]), "B", bootstrap=0)
        tied = rate(
            panel([(1, 0)] * 3 + [(0, 1)] + [(1, 1)] * 30 + [(0, 0)] * 30),
            "B",
            bootstrap=0,
        )
        self.assertEqual(base["ratings"][0]["rating"], tied["ratings"][0]["rating"])

    def test_no_discordance_means_no_rating(self) -> None:
        with self.assertRaisesRegex(ValueError, "disconnected"):
            rate(panel([(0, 0), (1, 1)]), "B", bootstrap=0)

    def test_connectivity_and_separation_are_distinct(self) -> None:
        edges = [(0, 1, 1.0, 0.0), (1, 2, 1.0, 0.0)]
        self.assertEqual(components(3, edges), [[0, 1, 2]])
        self.assertEqual(len(components(3, edges, directed=True)), 3)
        self.assertEqual(
            components(4, [(0, 1, 1.0, 1.0), (2, 3, 1.0, 1.0)]), [[0, 1], [2, 3]]
        )

    def test_record_order_does_not_change_ratings(self) -> None:
        data = simulated(families_per_domain=5)
        original = rate(data, "simulated-reference", bootstrap=0)
        for key in ("tasks", "provers", "results"):
            random.Random(5).shuffle(data[key])
        shuffled = rate(data, "simulated-reference", bootstrap=0)
        self.assertEqual(original["ratings"], shuffled["ratings"])

    def test_copying_variants_preserves_weight_and_uncertainty(self) -> None:
        data = simulated(families_per_domain=10)
        expected = rate(data, "simulated-reference", bootstrap=100)
        copied = copy.deepcopy(data)
        for task in data["tasks"]:
            copied["tasks"].append(dict(task, id=task["id"] + "-copy"))
        for row in data["results"]:
            copied["results"].append(dict(row, task=row["task"] + "-copy"))
        actual = rate(copied, "simulated-reference", bootstrap=100)
        self.assertEqual(expected["ratings"], actual["ratings"])

    def test_repeating_deterministic_trials_preserves_weight(self) -> None:
        data = panel([(1, 0)] * 3 + [(0, 1)] * 2)
        before = rate(data, "B", bootstrap=0)
        data["seeds"].append(1)
        data["results"] += [dict(row, seed=1) for row in list(data["results"])]
        after = rate(data, "B", bootstrap=0)
        self.assertEqual(before["ratings"], after["ratings"])

    def test_simulation_recovers_strength_and_reports_intervals(self) -> None:
        report = rate(simulated(), "simulated-reference", bootstrap=100, seed=3)
        expected = {
            "simulated-strong": 1800,
            "simulated-reference": 1500,
            "simulated-weak": 1200,
        }
        self.assertTrue(report["bootstrap"]["intervals_available"])
        for row in report["ratings"]:
            self.assertLess(abs(row["rating"] - expected[row["prover"]]), 40)
            self.assertLessEqual(row["interval95"][0], expected[row["prover"]])
            self.assertGreaterEqual(row["interval95"][1], expected[row["prover"]])
        self.assertTrue(any("SIMULATED" in w for w in report["warnings"]))

    def test_sparse_bootstrap_does_not_discard_disconnected_draws(self) -> None:
        report = rate(panel([(1, 0), (0, 1)] + [(0, 0)] * 8), "B", bootstrap=100)
        self.assertGreater(report["bootstrap"]["disconnected_draws"], 0)
        self.assertIsNone(report["ratings"][0]["interval95"])

    def test_domains_get_equal_weight_despite_different_sizes(self) -> None:
        data = panel([(1, 0)] + [(0, 1)] * 20)
        data["tasks"][0]["domain"] = "other-domain"
        report = rate(data, "B", bootstrap=0)
        self.assertEqual([r["rating"] for r in report["ratings"]], [1500, 1500])
        for row in report["ratings"]:
            self.assertAlmostEqual(row["balanced_solve_rate"], 0.5)


class RatingDataTests(unittest.TestCase):
    def test_identical_tasks_cannot_become_independent_families(self) -> None:
        data = panel([(1, 0), (0, 1)])
        data["tasks"][1]["sha256"] = data["tasks"][0]["sha256"]
        with self.assertRaisesRegex(ValueError, "fingerprints"):
            validate(data)

    def test_missing_and_duplicate_attempts_rejected(self) -> None:
        for mutation in (
            lambda d: d["results"].pop(),
            lambda d: d["results"].append(d["results"][0]),
        ):
            data = panel([(1, 0), (0, 1)])
            mutation(data)
            with self.assertRaises(ValueError):
                validate(data)

    def test_invalid_status_or_unchecked_success_rejected(self) -> None:
        for update in (
            {"status": "cancelled"},
            {"checker_accepted": False},
            {"elapsed_seconds": 11},
            {"elapsed_seconds": float("nan")},
            {"elapsed_seconds": True},
            {"artifact_sha256": None},
        ):
            data = panel([(1, 0), (0, 1)])
            data["results"][0].update(update)
            with self.assertRaises(ValueError):
                validate(data)

    def test_budget_validation(self) -> None:
        for budget in (0, -1, float("inf"), float("nan"), True):
            data = panel([(1, 0)])
            data["protocol"]["budget_seconds"] = budget
            with self.assertRaises(ValueError):
                validate(data)

    def test_duplicate_task_and_cross_domain_family_rejected(self) -> None:
        data = panel([(1, 0), (0, 1)])
        data["tasks"][1]["family"] = "0"
        data["tasks"][1]["domain"] = "different"
        with self.assertRaises(ValueError):
            validate(data)
        data = panel([(1, 0)])
        data["tasks"].append(data["tasks"][0])
        with self.assertRaises(ValueError):
            validate(data)

    def test_merge_requires_same_protocol_and_disjoint_provers(self) -> None:
        data = panel([(1, 0), (0, 1)])
        halves = []
        for name in ("A", "B"):
            part = copy.deepcopy(data)
            part["provers"] = [p for p in part["provers"] if p["id"] == name]
            part["results"] = [r for r in part["results"] if r["prover"] == name]
            halves.append(part)
        self.assertEqual(len(merge(halves)["results"]), 4)
        with self.assertRaises(ValueError):
            merge([halves[0], halves[0]])
        halves[1]["protocol"]["budget_seconds"] = 20
        with self.assertRaisesRegex(ValueError, "protocol"):
            merge(halves)

    def test_generator_reproducibility_and_family_assignment(self) -> None:
        first = smoke_suite(seed=3, variants=2)
        self.assertEqual(first, smoke_suite(seed=3, variants=2))
        self.assertNotEqual(first, smoke_suite(seed=4, variants=2))
        self.assertEqual(len(first["tasks"]), 32)
        self.assertEqual(len({t["family"] for t in first["tasks"]}), 16)
        self.assertFalse(any("import " in t["prefix"] for t in first["tasks"]))

    def test_cli_demo_and_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(main(["demo", temporary, "--bootstrap", "0"]), 0)
            root = Path(temporary)
            self.assertEqual(
                main(
                    [
                        "rate",
                        str(root / "simulated-results.json"),
                        "--anchor",
                        "simulated-reference",
                        "--output",
                        str(root / "again.json"),
                        "--bootstrap",
                        "0",
                    ]
                ),
                0,
            )
            self.assertTrue((root / "simulated-report.md").exists())


class RatingRunnerTests(unittest.TestCase):
    def test_false_verified_claim_never_supplies_a_candidate(self) -> None:
        with self.assertRaises(ValueError):
            candidate_from_result({"status": "verified"}, "source", "agdaprover")
        self.assertIsNone(
            candidate_from_result({"status": "verified"}, "source", "candidate-json")
        )

    def test_fixed_type_and_assumptions_cannot_be_modified(self) -> None:
        task = smoke_suite(variants=1)["tasks"][0]
        valid = task["prefix"] + task["reference"]
        validate_candidate(task, valid)
        for candidate in (
            valid.replace("Set", "Set₁"),
            task["prefix"] + "postulate goal : Set\n",
            task["prefix"] + "{-# TERMINATING #-}\ngoal = goal\n",
            task["prefix"] + "import Agda.Builtin.TrustMe\n",
            task["prefix"] + task["starter"],
        ):
            with self.assertRaises(ValueError):
                validate_candidate(task, candidate)

    @unittest.skipUnless(os.name == "posix", "POSIX process groups required")
    def test_timeout_kills_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                process(
                    [sys.executable, "-c", "import time; time.sleep(5)"],
                    Path(directory),
                    0.05,
                )

    def test_missing_worker_is_a_harness_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(HarnessError):
                process(["/nonexistent/ppr-worker"], Path(directory), 1)


@unittest.skipUnless(AGDA, "Agda is required")
class LiveRatingTests(unittest.TestCase):
    def test_every_generated_reference_checks(self) -> None:
        assert AGDA is not None
        validate_suite(smoke_suite(seed=57, variants=2), AGDA)

    def test_fresh_checker_rejects_unsolved_metas_and_recursion(self) -> None:
        assert AGDA is not None
        task = smoke_suite(variants=1)["tasks"][0]
        for body in ("goal = _\n", "goal = {!!}\n", "goal = goal\n"):
            accepted, _ = check_source(task["prefix"] + body, AGDA, 10)
            self.assertFalse(accepted)

    @unittest.skipUnless(PROVER, "PPR_TEST_PROVER is required")
    def test_real_agdaprover_adapter_and_independent_checker(self) -> None:
        assert AGDA is not None
        suite = smoke_suite(variants=1)
        suite["tasks"] = suite["tasks"][:1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Use an absolute PYTHONPATH so the worker runs outside this checkout.
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            config = [
                {
                    "id": "AgdaProver-test",
                    "revision": "test-fixture",
                    "adapter": "agdaprover",
                    "argv": [
                        PROVER,
                        "prove-prefix",
                        "{source}",
                        "--agda",
                        "{agda}",
                        "--timeout",
                        "{budget}",
                    ],
                }
            ]
            (root / "suite.json").write_text(json.dumps(suite))
            (root / "provers.json").write_text(json.dumps(config))
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "prover_strength",
                    "run",
                    str(root / "suite.json"),
                    str(root / "provers.json"),
                    str(root / "results.json"),
                    "--agda",
                    AGDA,
                    "--budget",
                    "30",
                    "--environment-id",
                    "integration-test",
                ],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            data = json.loads((root / "results.json").read_text())
            self.assertEqual(data["results"][0]["status"], "verified", data)
            self.assertTrue(data["results"][0]["checker_accepted"])

    def test_generic_adapter_does_not_trust_a_false_claim(self) -> None:
        assert AGDA is not None
        suite = smoke_suite(variants=1)
        suite["tasks"] = suite["tasks"][:1]
        with tempfile.TemporaryDirectory() as directory:
            prover = {
                "id": "liar",
                "revision": "test-fixture",
                "adapter": "candidate-json",
                "argv": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'status':'verified'}))",
                ],
            }
            data = run(
                suite,
                [prover],
                agda=AGDA,
                budget=5,
                environment_id="test",
                seeds=[0],
                artifacts=Path(directory) / "artifacts",
            )
            self.assertNotEqual(data["results"][0]["status"], "verified")


if __name__ == "__main__":
    unittest.main()
