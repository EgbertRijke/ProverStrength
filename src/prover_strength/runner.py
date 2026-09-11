"""Local POSIX runner: immutable tasks, process-group wall limits, fresh checking.

This is an evaluator for trusted local executables, not a hostile-code sandbox.
Competition-wide CPU/memory/network quotas belong to an external supervisor.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from . import projects
from .adapters import agdaprover_candidate
from .data import SCHEMA, digest, identifier, positive, validate
from .process import MAX_OUTPUT, HarnessError, OutputLimitError, process
from .tasks import HEADER, suite_metadata

FORBIDDEN = re.compile(r"\b(import|postulate|primitive|unquoteDecl|unquoteDef)\b|\{-#")
CHECK_FLAGS = [
    "--safe",
    "--without-K",
    "--exact-split",
    "--no-libraries",
    "--no-default-libraries",
    "--ignore-all-interfaces",
]


def executable(command: str) -> str:
    found = shutil.which(command)
    if not found:
        raise HarnessError(f"executable not found: {command}")
    # Invocation paths can select environments (notably a venv's Python).
    # Hashing still follows the file, but resolving this symlink before exec
    # would silently replace the requested runtime with the system one.
    return os.path.abspath(found)


def file_sha256(path: str) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_source(
    source: str,
    agda: str,
    seconds: float,
    *,
    max_output: int = MAX_OUTPUT,
    task: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="ppr-check-") as directory:
        root = Path(directory)
        if task is not None and "project" in task:
            projects.materialize(task, source, root)
            arguments = projects.checker_arguments(task, root)
        else:
            (root / "Task.agda").write_text(source, encoding="utf-8")
            arguments = [*CHECK_FLAGS, "-i", str(root), "Task.agda"]
        code, out, err = process(
            [agda, *arguments],
            root,
            seconds,
            max_output=max_output,
        )
        # Agda 2.8 uses 42 for TCM rejection. Code 1 means unknown failure;
        # option/command/internal failures and signals must abort measurement.
        # See Agda.Interaction.ExitCode at the pinned v2.8.0 tag.
        if code not in (0, 42):
            raise HarnessError(
                f"Agda checker failed with exit code {code}: {(out + err)[-2000:]}"
            )
        return code == 0, (out + err)[-8000:]


def validate_suite(
    suite: dict[str, Any],
    agda: str,
    *,
    reference_budget: float = 60,
    max_output: int = MAX_OUTPUT,
) -> None:
    positive(reference_budget, "reference_budget")
    if suite.get("schema_version") not in {
        "portable-prover-rating.suite.v1",
        projects.SCHEMA,
    }:
        raise ValueError("unsupported suite schema")
    identifier(suite["track"], "track")
    if not suite["tasks"]:
        raise ValueError("empty suite")
    seen = set()
    tasks = projects.bind_tasks(suite)
    if suite.get("schema_version") == projects.SCHEMA:
        code, version, _ = process(
            [agda, "--numeric-version"], Path.cwd(), reference_budget
        )
        if code or version.strip() != suite["agda_version"]:
            raise HarnessError("project bank requires its pinned Agda version")
    for task in tasks:
        for key in ("id", "domain", "family", "prefix", "starter", "reference"):
            identifier(task[key], key)
        if task["id"] in seen:
            raise ValueError("duplicate task id")
        seen.add(task["id"])
        prefix = task["prefix"]
        if "project" not in task and (
            not prefix.startswith(HEADER) or not prefix.endswith("\n")
        ):
            raise ValueError("portable Agda tasks require the fixed Task module header")
        remaining = re.sub(
            r"\{-# BUILTIN EQUALITY [A-Za-z0-9]+ #-\}", "", prefix[len(HEADER) :]
        )
        if ("project" not in task and FORBIDDEN.search(remaining)) or FORBIDDEN.search(
            task["starter"]
        ):
            raise ValueError("task uses imports, assumptions, or unapproved pragmas")
        if "project" not in task and not re.search(r"^goal\s*:", prefix, re.MULTILINE):
            raise ValueError("task must fix the type of goal in its prefix")
        validate_candidate(task, prefix + task["reference"])
        accepted, diagnostic = check_source(
            prefix + task["reference"],
            agda,
            reference_budget,
            max_output=max_output,
            task=task,
        )
        if not accepted:
            raise HarnessError(f"invalid reference for {task['id']}: {diagnostic}")


def candidate_from_result(
    payload: dict[str, Any], source: str, adapter: str
) -> str | None:
    if adapter == "candidate-json":
        candidate = payload.get("candidate")
        if candidate is not None and not isinstance(candidate, str):
            raise ValueError("candidate must be a complete source string or null")
        return candidate
    if adapter != "agdaprover":
        raise ValueError(f"unknown adapter: {adapter}")
    if payload.get("status") != "verified":
        return None
    patch = payload.get("patch")
    if not isinstance(patch, dict):
        raise ValueError("AgdaProver verified result lacks a patch")
    return agdaprover_candidate(source, patch)


def validate_candidate(task: dict[str, Any], candidate: str) -> None:
    prefix = task["prefix"]
    if not candidate.startswith(prefix):
        raise ValueError("candidate changed the fixed context or goal type")
    body = candidate[len(prefix) :]
    if FORBIDDEN.search(body):
        raise ValueError("candidate adds imports, assumptions, or compiler pragmas")
    # The compiler, with --safe, rejects all unresolved metas, termination and
    # positivity violations. This source check is only an additional guard.
    if "{!!}" in body or "{!" in body:
        raise ValueError("candidate retains an interaction hole")


def run(
    suite: dict[str, Any],
    provers: list[dict[str, Any]],
    *,
    agda: str,
    budget: float,
    environment_id: str,
    seeds: list[int],
    artifacts: Path,
    order_seed: int = 0,
    reference_budget: float = 60,
    max_output: int = MAX_OUTPUT,
) -> dict[str, Any]:
    if os.name != "posix":
        raise HarnessError("local process-group supervision requires POSIX")
    positive(budget, "budget")
    positive(reference_budget, "reference_budget")
    if type(max_output) is not int or max_output <= 0:
        raise ValueError("output budget must be a positive integer")
    identifier(environment_id, "environment_id")
    if (
        not seeds
        or any(type(s) is not int for s in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("seeds must be distinct integers")
    if not provers or len({p["id"] for p in provers}) != len(provers):
        raise ValueError("prover ids must be nonempty and distinct")
    provers = [dict(prover) for prover in provers]
    agda = executable(agda)
    for prover in provers:
        identifier(prover["id"], "prover id")
        identifier(prover["revision"], "prover revision")
        if prover["adapter"] not in {"agdaprover", "candidate-json"}:
            raise ValueError("unknown adapter")
        argv = prover["argv"]
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(v, str) for v in argv)
        ):
            raise ValueError("argv must be a nonempty list of strings")
        binary = executable(argv[0])
        prover["argv"] = [binary, *argv[1:]]
        prover["executable_sha256"] = file_sha256(binary)
    if artifacts.exists():
        raise ValueError(
            "artifact directory already exists; preserve prior measurements"
        )
    validate_suite(
        suite, agda, reference_budget=reference_budget, max_output=max_output
    )
    agda_hash = file_sha256(agda)
    code, version, _ = process([agda, "--numeric-version"], Path.cwd(), 10.0)
    if code:
        raise HarnessError("Agda version check failed")
    protocol = {
        "track": suite["track"],
        "budget_seconds": budget,
        "environment_id": environment_id,
        "checker_id": f"agda-{version.strip()}-sha256:{agda_hash}",
        "checker_flags": projects.FLAGS
        if suite.get("schema_version") == projects.SCHEMA
        else CHECK_FLAGS,
        "enforcement": "local-wall-stream-bounded-process-group-v2",
        "max_output_bytes": max_output,
        "reference_check_budget_seconds": reference_budget,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "suite_role": suite.get("role", "unclassified"),
    }
    artifacts.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": "prover-strength.run-manifest.v1",
        "suite_id": digest(suite),
        "protocol": protocol,
        "tasks": suite_metadata(suite),
        "provers": provers,
        "seeds": seeds,
        "order_seed": order_seed,
    }
    (artifacts / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # Full reference solutions remain with the evaluator. A worker receives
    # only its open entry and fixed context, never the bank or reference bodies.
    jobs = [
        (p, t, seed)
        for t in projects.bind_tasks(suite)
        for seed in seeds
        for p in provers
    ]
    random.Random(order_seed).shuffle(jobs)
    rows: list[dict[str, Any]] = []
    for prover, task, seed in jobs:
        started = time.monotonic()
        row: dict[str, Any] = {
            "prover": prover["id"],
            "task": task["id"],
            "seed": seed,
            "status": "unsolved",
            "checker_accepted": False,
        }
        artifact_id = digest([prover["id"], task["id"], seed])[:24]
        log: dict[str, Any] = {}
        try:
            with tempfile.TemporaryDirectory(prefix="ppr-task-") as directory:
                root = Path(directory)
                original = task["prefix"] + task["starter"]
                if "project" in task:
                    source_file = projects.materialize(task, original, root)
                else:
                    source_file = root / "Task.agda"
                    source_file.write_text(original, encoding="utf-8")
                replacements = {
                    "{source}": str(source_file),
                    "{budget}": str(budget),
                    "{seed}": str(seed),
                    "{agda}": agda,
                }
                argv = list(prover["argv"])
                argv[0] = executable(argv[0])
                for key, value in replacements.items():
                    argv = [arg.replace(key, value) for arg in argv]
                code, out, err = process(
                    argv,
                    root,
                    budget - (time.monotonic() - started),
                    seed=seed,
                    max_output=max_output,
                )
                log.update(argv=argv, exit_code=code, stdout=out, stderr=err)
                if "project" in task and not projects.unchanged(task, original, root):
                    raise HarnessError("contestant changed immutable project sources")
                try:
                    payload = json.loads(out)
                    if not isinstance(payload, dict):
                        raise ValueError("worker JSON must be an object")
                    candidate = candidate_from_result(
                        payload, original, prover["adapter"]
                    )
                    if candidate is None:
                        if payload.get("status") == "resource-exhausted":
                            row["status"] = "resource-exhausted"
                        elif code not in (0, 2):
                            row["status"] = "crash"
                    else:
                        validate_candidate(task, candidate)
                        accepted, diagnostic = check_source(
                            candidate,
                            agda,
                            budget - (time.monotonic() - started),
                            max_output=max_output,
                            task=task,
                        )
                        log["checker_diagnostic"] = diagnostic
                        elapsed = time.monotonic() - started
                        if accepted and elapsed <= budget:
                            row.update(
                                status="verified",
                                checker_accepted=True,
                                artifact_sha256=hashlib.sha256(
                                    candidate.encode("utf-8")
                                ).hexdigest(),
                            )
                            (artifacts / f"{artifact_id}.agda").write_text(
                                candidate, encoding="utf-8"
                            )
                        else:
                            row["status"] = "timeout" if elapsed > budget else "invalid"
                except (ValueError, TypeError, KeyError) as error:
                    row["status"] = "invalid" if code == 0 else "crash"
                    log["error"] = str(error)
        except TimeoutError as error:
            row["status"] = "timeout"
            log["error"] = str(error)
        except OutputLimitError as error:
            row["status"] = "resource-exhausted"
            log["error"] = str(error)
        except HarnessError as error:
            (artifacts / "aborted.json").write_text(
                json.dumps(
                    {
                        "schema_version": "prover-strength.aborted-run.v1",
                        "status": "harness-error",
                        "completed_trials": len(rows),
                        "trial": row,
                        "error": str(error),
                        "log": log,
                        "protocol": protocol,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            raise
        row["elapsed_seconds"] = time.monotonic() - started
        if row["status"] == "verified" and row["elapsed_seconds"] > budget:
            row.update(status="timeout", checker_accepted=False)
            row.pop("artifact_sha256", None)
        (artifacts / f"{artifact_id}.json").write_text(
            json.dumps(log, indent=2) + "\n", encoding="utf-8"
        )
        rows.append(row)
        # Preserve completed outcomes if the evaluation is interrupted.
        with (artifacts / "completed.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    if file_sha256(agda) != agda_hash or any(
        file_sha256(p["argv"][0]) != p["executable_sha256"] for p in provers
    ):
        (artifacts / "aborted.json").write_text(
            json.dumps(
                {
                    "schema_version": "prover-strength.aborted-run.v1",
                    "status": "harness-error",
                    "completed_trials": len(rows),
                    "error": "an evaluated executable changed during the run",
                    "protocol": protocol,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise HarnessError("an evaluated executable changed during the run")
    result = {
        "schema_version": SCHEMA,
        "suite_id": digest(suite),
        "protocol": protocol,
        "tasks": suite_metadata(suite),
        "seeds": seeds,
        "provers": provers,
        "results": rows,
        "order_seed": order_seed,
    }
    validate(result)
    return result
