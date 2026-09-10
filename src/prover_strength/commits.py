"""Portable commit measurement and a bounded, restartable local commit queue."""

from __future__ import annotations

import fcntl
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .campaigns import validate_campaign
from .commit_worker import hashes, save
from .data import digest, identifier
from .history import record
from .runner import executable, file_sha256


def git(repository: Path, *args: str) -> str:
    return (
        subprocess.check_output(["git", "-C", str(repository), *args], timeout=30)
        .decode()
        .strip()
    )


def revision(repository: Path, ref: str) -> str:
    value = git(
        repository, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"
    )
    if not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError("expected a SHA-1 Git commit identity")
    return value


def snapshot(repository: Path, commit: str, output: Path, name: str) -> Path:
    archive = output / (name + ".tar")
    with archive.open("xb") as stream:
        subprocess.run(
            ["git", "-C", str(repository), "archive", "--format=tar", commit],
            stdout=stream,
            timeout=60,
            check=True,
        )
    target = output / name
    target.mkdir()
    with tarfile.open(archive) as contents:
        for member in contents.getmembers():
            if not (member.isfile() or member.isdir()):
                raise ValueError(
                    "measurement snapshots do not admit links or special files"
                )
            if not (target / member.name).resolve().is_relative_to(target.resolve()):
                raise ValueError("snapshot member escapes its directory")
        contents.extractall(target, filter="data")
    return target


def worker_environment() -> dict[str, str]:
    # In particular: no GitHub tokens, credentials, Python path overrides, or
    # experimental AgdaProver flags inherited from the scheduler/publisher.
    names = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "LD_LIBRARY_PATH")
    env = {k: os.environ[k] for k in names if k in os.environ}
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        LANG="C.UTF-8",
        LC_ALL="C.UTF-8",
    )
    return env


def command(source: Path, module: str) -> list[str]:
    return [
        sys.executable,
        "-B",
        "-S",
        "-c",
        f"import sys; sys.path.insert(0, {str(source / 'src')!r}); from {module} import main; raise SystemExit(main())",
    ]


def measure(
    product_repository: Path,
    evaluator_repository: Path,
    output: Path,
    *,
    ref: str,
    agda: str,
    environment_id: str,
    campaign: dict[str, Any],
    history: Path | None = None,
    network_policy: str = "external-supervisor-unspecified",
) -> Path:
    validate_campaign(campaign)
    identifier(environment_id, "environment_id")
    evaluator_commit = campaign["evaluator_commit"]
    suite_path, suite_hash = campaign["suite"]["path"], campaign["suite"]["sha256"]
    profile = campaign["profile"]
    budget = profile["budget_seconds"]
    commit = revision(product_repository, ref)
    agda = executable(agda)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    product = snapshot(product_repository, commit, output, "product")
    evaluator = snapshot(evaluator_repository, evaluator_commit, output, "evaluator")
    if file_sha256(str(evaluator / suite_path)) != suite_hash:
        raise ValueError("frozen suite checksum mismatch")
    worker = Path(__file__).with_name("commit_worker.py")
    shutil.copyfile(worker, output / "driver.py")
    suite = json.loads((evaluator / suite_path).read_text())
    python_hash = file_sha256(str(Path(sys.executable).resolve()))
    metadata = {
        "schema_version": "prover-strength.commit-observation.v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "product_commit": commit,
        "product_tree": git(product_repository, "rev-parse", commit + "^{tree}"),
        "evaluator_commit": evaluator_commit,
        "evaluator_tree": git(
            evaluator_repository, "rev-parse", evaluator_commit + "^{tree}"
        ),
        "driver_sha256": file_sha256(str(output / "driver.py")),
        "controller_sha256": file_sha256(__file__),
        "source_hashes": {"product": hashes(product), "evaluator": hashes(evaluator)},
        "archive_sha256": {
            n: file_sha256(str(output / (n + ".tar"))) for n in ("product", "evaluator")
        },
        "suite_id": digest(suite),
        "suite_file_sha256": suite_hash,
        "profile": profile,
        "campaign": campaign,
        "environment": {
            "id": environment_id,
            "platform": platform.platform(),
            "python": sys.version,
            "python_sha256": python_hash,
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "network": network_policy,
            "workers": 1,
            "python_hash_seed": 0,
            "product_environment_overrides": {},
            "site_packages": "disabled in workers",
            "cache_policy": "fresh task/check directories; immutable sources; installed Agda builtins",
            "locale": "C.UTF-8",
        },
    }
    save(output / "observation.json", metadata)
    provers = []
    for role, source, revision_id in (
        ("reference", evaluator, evaluator_commit),
        ("participant", product, commit),
    ):
        spec = campaign[role]
        provers.append(
            {
                "id": spec["id"],
                "revision": revision_id,
                "adapter": spec["adapter"],
                "argv": command(source, spec["module"]) + spec["arguments"],
            }
        )
    save(output / "provers.json", provers)
    save(
        output / "request.json",
        {
            "suite_path": suite_path,
            "agda": agda,
            "budget": budget,
            "anchor": campaign["reference"]["id"],
        },
    )
    argv = [sys.executable, "-B", "-S", str(output / "driver.py"), str(output)]
    print(
        f"Measuring {commit} in {campaign['id']} ({budget:g} seconds/task)", flush=True
    )
    with subprocess.Popen(argv, env=worker_environment()) as child:
        try:
            code = child.wait()
        except KeyboardInterrupt:
            child.send_signal(signal.SIGINT)
            child.wait()
            raise
    if code:
        raise RuntimeError(
            f"measurement worker failed ({code}); evidence retained at {output}"
        )
    for name, before in metadata["source_hashes"].items():
        if hashes(output / name) != before:
            raise ValueError("frozen source integrity changed")
    if history is not None:
        return record(output, history)
    return output


def pending_commits(repository: Path, first: str, tip: str) -> list[str]:
    start, end = revision(repository, first), revision(repository, tip)
    reachable = subprocess.run(
        ["git", "-C", str(repository), "merge-base", "--is-ancestor", start, end],
        timeout=30,
    )
    if reachable.returncode:
        raise ValueError("tracking start is not an ancestor of the selected tip")
    mainline = git(repository, "rev-list", "--first-parent", end).splitlines()
    if start not in mainline:
        raise ValueError("tracking start is not on the first-parent history")
    later = git(
        repository, "rev-list", "--reverse", "--first-parent", start + ".." + end
    )
    return [start, *later.splitlines()]


def measure_pending(
    product: Path,
    evaluator: Path,
    queue: Path,
    *,
    campaign: dict[str, Any],
    tip: str,
    agda: str,
    environment_id: str,
    history: Path,
    limit: int = 2,
    network_policy: str = "external-supervisor-unspecified",
) -> dict[str, Any]:
    validate_campaign(campaign)
    if type(limit) is not int or limit < 1:
        raise ValueError("batch limit must be a positive integer")
    queue.mkdir(parents=True, exist_ok=True)
    # The lock is kernel-owned, not a stale PID/lease guess. Hosted Actions also
    # serializes this workflow; it never cancels a running measurement for a push.
    with (queue / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "another measurement controller owns this queue"
            ) from error
        commits = pending_commits(product, campaign["first_commit"], tip)
        identity = digest(
            {
                "campaign": campaign,
                "environment": environment_id,
                "agda_sha256": file_sha256(executable(agda)),
                "driver": file_sha256(
                    str(Path(__file__).with_name("commit_worker.py"))
                ),
                "network": network_policy,
                "python": sys.version,
            }
        )
        campaign_root = queue / identity
        campaign_root.mkdir(exist_ok=True)
        attempted: list[str] = []
        completed: list[str] = []
        unresolved: list[str] = []
        for commit in commits:
            receipt = campaign_root / (commit + ".json")
            if receipt.exists():
                state = json.loads(receipt.read_text())
                if (
                    state.get("schema_version") != "prover-strength.queued-commit.v1"
                    or state.get("commit") != commit
                ):
                    raise ValueError("invalid queue receipt")
                if state.get("status") == "completed":
                    archived = state.get("observation", "")
                    if (
                        not re.fullmatch(r"[a-f0-9]{64}", archived)
                        or not (history / archived / "point.json").is_file()
                    ):
                        raise ValueError(
                            "completed queue entry has no archived observation"
                        )
                    completed.append(commit)
                else:
                    unresolved.append(commit)
                continue
            if len(attempted) >= limit:
                continue
            save(
                receipt,
                {
                    "schema_version": "prover-strength.queued-commit.v1",
                    "commit": commit,
                    "status": "started",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            destination = campaign_root / commit
            attempted.append(commit)
            try:
                archived_path = measure(
                    product,
                    evaluator,
                    destination,
                    ref=commit,
                    agda=agda,
                    environment_id=environment_id,
                    campaign=campaign,
                    history=history,
                    network_policy=network_policy,
                )
                state = {
                    "schema_version": "prover-strength.queued-commit.v1",
                    "commit": commit,
                    "status": "completed",
                    "observation": archived_path.name,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
                completed.append(commit)
            except (
                RuntimeError,
                ValueError,
                OSError,
                subprocess.SubprocessError,
            ) as error:
                state = {
                    "schema_version": "prover-strength.queued-commit.v1",
                    "commit": commit,
                    "status": "harness-error",
                    "error": str(error),
                }
                unresolved.append(commit)
            temporary = receipt.with_suffix(".next")
            save(temporary, state)
            temporary.replace(receipt)
        return {
            "schema_version": "prover-strength.commit-batch.v1",
            "campaign": identity,
            "eligible": commits,
            "attempted": attempted,
            "completed": completed,
            "unresolved": unresolved,
            "pending": [
                c for c in commits if c not in completed and c not in unresolved
            ],
        }
