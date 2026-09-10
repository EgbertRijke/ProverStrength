"""Boundary regressions independent of a solver or installed Agda."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from prover_strength.adapters import agdaprover_candidate
from prover_strength.benchmark import smoke_suite
from prover_strength.process import HarnessError, OutputLimitError, process
from prover_strength.runner import check_source, run, validate_suite


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = "λ goal = {!!}\n"
        self.edit = {
            "schema_version": "agdaprover.reconstruction.p0.v1",
            "source_range": [10, 14],
            "original": "{!!}",
            "replacement": "refl",
        }

    def test_unicode_offsets_and_versioned_reconstruction(self) -> None:
        self.assertEqual(
            agdaprover_candidate(self.source, self.edit), "λ goal = refl\n"
        )

    def test_stale_malformed_and_unknown_edits_rejected(self) -> None:
        for change in (
            {"schema_version": "future"},
            {"source_range": [True, 14]},
            {"source_range": [0, 14]},
            {"source_range": [10, 100]},
            {"source_range": [14, 10]},
            {"source_range": "10:14"},
            {"original": "wrong"},
            {"replacement": None},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                agdaprover_candidate(self.source, self.edit | change)


@unittest.skipUnless(os.name == "posix", "POSIX process groups required")
class ProcessTests(unittest.TestCase):
    def call(self, code: str, seconds: float = 2, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            return process(
                [sys.executable, "-c", code], Path(directory), seconds, **kwargs
            )

    def test_output_flood_is_stopped_while_running(self) -> None:
        started = time.monotonic()
        with self.assertRaises(OutputLimitError):
            self.call(
                "import os\nwhile True: os.write(1, b'x' * 4096)", max_output=10000
            )
        self.assertLess(time.monotonic() - started, 2)

    def test_stdout_and_stderr_share_budget(self) -> None:
        with self.assertRaises(OutputLimitError):
            self.call(
                "import os; os.write(1,b'x'*60); os.write(2,b'y'*60)", max_output=100
            )

    def test_exact_output_limit_is_accepted(self) -> None:
        code, out, err = self.call("import os; os.write(1,b'x'*100)", max_output=100)
        self.assertEqual((code, out, err), (0, "x" * 100, ""))

    def test_larger_explicit_output_budget_is_supported(self) -> None:
        _, out, _ = self.call("import os; os.write(1,b'x'*200000)", max_output=300000)
        self.assertEqual(len(out), 200000)

    def test_closed_streams_do_not_disable_deadline(self) -> None:
        with self.assertRaises(TimeoutError):
            self.call("import os,time; os.close(1); os.close(2); time.sleep(5)", 0.1)

    def test_inherited_pipes_do_not_hang_after_parent_exit(self) -> None:
        with self.assertRaises(TimeoutError):
            self.call("import os,time\nif os.fork() == 0: time.sleep(5)", 0.1)

    def test_process_group_is_killed_on_output_exhaustion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "survivor"
            code = (
                "import os,time,pathlib\n"
                "if os.fork() == 0:\n"
                f" time.sleep(.3); pathlib.Path({str(marker)!r}).touch()\n"
                "else:\n while True: os.write(1,b'x'*4096)\n"
            )
            with self.assertRaises(OutputLimitError):
                self.call(code, max_output=10000)
            time.sleep(0.4)
            self.assertFalse(marker.exists())

    def test_bad_budgets(self) -> None:
        for budget in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                self.call("pass", budget)
        for size in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.call("pass", max_output=size)


class CheckerTests(unittest.TestCase):
    def run_fixture(self, root: Path, worker, checker):
        suite = smoke_suite(variants=1)
        suite["tasks"] = suite["tasks"][:1]
        prover = {
            "id": "p",
            "revision": "v1",
            "adapter": "candidate-json",
            "argv": [sys.executable],
        }
        with (
            patch("prover_strength.runner.validate_suite"),
            patch(
                "prover_strength.runner.process", side_effect=[(0, "2.8.0", ""), worker]
            ),
            patch("prover_strength.runner.check_source", side_effect=checker),
        ):
            return run(
                suite,
                [prover],
                agda=sys.executable,
                budget=5,
                environment_id="test",
                seeds=[0],
                artifacts=root / "artifacts",
            )

    def test_output_exhaustion_retains_complete_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_fixture(root, OutputLimitError("too large"), None)
            self.assertEqual(result["results"][0]["status"], "resource-exhausted")
            self.assertEqual(len(result["results"]), 1)
            manifest = json.loads((root / "artifacts/manifest.json").read_text())
            self.assertEqual(manifest["protocol"], result["protocol"])
            self.assertEqual(len(manifest["provers"][0]["executable_sha256"]), 64)

    def test_checker_crash_retains_abort_not_scored_result(self) -> None:
        task = smoke_suite(variants=1)["tasks"][0]
        worker = (0, json.dumps({"candidate": task["prefix"] + task["reference"]}), "")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(HarnessError):
                self.run_fixture(root, worker, HarnessError("checker crashed"))
            abort = json.loads((root / "artifacts/aborted.json").read_text())
            self.assertEqual(abort["status"], "harness-error")
            self.assertEqual(abort["completed_trials"], 0)
            self.assertFalse((root / "artifacts/completed.jsonl").exists())

    def test_checker_signal_and_unexpected_exit_abort(self) -> None:
        for exit_code in (-9, -11, 1, 2, 71, 113, 127, 154):
            with patch(
                "prover_strength.runner.process", return_value=(exit_code, "", "crash")
            ):
                with self.assertRaises(HarnessError):
                    check_source("source", "agda", 1)

    def test_ordinary_checker_rejection_is_not_a_harness_crash(self) -> None:
        with patch(
            "prover_strength.runner.process", return_value=(42, "", "type error")
        ):
            self.assertEqual(check_source("source", "agda", 1), (False, "type error"))

    def test_reference_body_obeys_same_source_policy(self) -> None:
        suite = smoke_suite(variants=1)
        suite["tasks"] = [copy.deepcopy(suite["tasks"][0])]
        suite["tasks"][0]["reference"] = "{-# TERMINATING #-}\ngoal = goal\n"
        with patch("prover_strength.runner.check_source") as checker:
            with self.assertRaises(ValueError):
                validate_suite(suite, "agda")
            checker.assert_not_called()

    def test_reference_budget_is_explicit(self) -> None:
        suite = smoke_suite(variants=1)
        suite["tasks"] = suite["tasks"][:1]
        with patch(
            "prover_strength.runner.check_source", return_value=(True, "")
        ) as checker:
            validate_suite(suite, "agda", reference_budget=300, max_output=12345)
            self.assertEqual(checker.call_args.args[2], 300)
            self.assertEqual(checker.call_args.kwargs["max_output"], 12345)

    def test_harness_error_does_not_become_scored_failure(self) -> None:
        suite = smoke_suite(variants=1)
        suite["tasks"] = suite["tasks"][:1]
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "prover_strength.runner.validate_suite",
                side_effect=HarnessError("broken"),
            ):
                with self.assertRaises(HarnessError):
                    run(
                        suite,
                        [
                            {
                                "id": "p",
                                "revision": "v1",
                                "adapter": "candidate-json",
                                "argv": [sys.executable],
                            }
                        ],
                        agda=sys.executable,
                        budget=1,
                        environment_id="test",
                        seeds=[0],
                        artifacts=Path(directory) / "out",
                    )
                self.assertFalse((Path(directory) / "out").exists())
