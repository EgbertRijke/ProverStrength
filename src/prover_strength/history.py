"""Append-only local observations and a read-only, dependency-free live chart."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .data import digest, validate
from .runner import file_sha256


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def effort(run: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counters are diagnostic self-reports; missing failed effort is not zero."""
    fields: dict[str, list[int]] = {"actions_expanded": [], "verifier_calls": []}
    for row in rows:
        identity = digest([row["prover"], row["task"], row["seed"]])[:24]
        log = read_json(run / "artifacts" / (identity + ".json"))
        try:
            payload = json.loads(log.get("stdout", ""))
            counters = {
                "actions_expanded": payload.get("cost", {}).get("actions_expanded"),
                "verifier_calls": payload.get("verifier_calls"),
            }
        except (ValueError, AttributeError, TypeError):
            counters = {}
        for field, values in fields.items():
            value = counters.get(field)
            if type(value) is int and value >= 0:
                values.append(value)
    result: dict[str, Any] = {
        "accounting": "agdaprover.p0.v1-self-reported",
        "assigned_trials": len(rows),
        "cpu_seconds": None,
    }
    for field, values in fields.items():
        result[field] = {
            "observed": sum(values),
            "known_trials": len(values),
            "unknown_trials": len(rows) - len(values),
            "total": sum(values) if len(values) == len(rows) else None,
        }
    total = result["actions_expanded"]["total"]
    solved = sum(row["status"] == "verified" for row in rows)
    result["proofs_per_1000_actions"] = 1000 * solved / total if total else None
    return result


def observation(run: Path) -> dict[str, Any]:
    metadata = read_json(run / "observation.json")
    receipt = read_json(run / "completed.json")
    if metadata.get("schema_version") != "prover-strength.commit-observation.v1":
        raise ValueError("unsupported commit observation")
    if receipt.get("source_integrity") != "unchanged":
        raise ValueError("observation lacks source integrity receipt")
    for name in ("results", "ratings"):
        if file_sha256(str(run / (name + ".json"))) != receipt[name + "_sha256"]:
            raise ValueError(f"changed {name} evidence")
    result, report = read_json(run / "results.json"), read_json(run / "ratings.json")
    validate(result)
    if not result["protocol"].get("synthetic"):
        for row in result["results"]:
            if row["status"] != "verified":
                continue
            name = digest([row["prover"], row["task"], row["seed"]])[:24]
            proof = run / "artifacts" / (name + ".agda")
            if file_sha256(str(proof)) != row["artifact_sha256"]:
                raise ValueError("changed independently checked proof artifact")
    if report["input_sha256"] != digest(result):
        raise ValueError("rating does not describe these outcomes")
    if metadata["suite_id"] != result["suite_id"]:
        raise ValueError("commit receipt describes another suite")
    matches = [
        p for p in result["provers"] if p["revision"] == metadata["product_commit"]
    ]
    if len(matches) != 1:
        raise ValueError("commit observation requires one matching product contestant")
    contestant = matches[0]
    rows = [r for r in result["results"] if r["prover"] == contestant["id"]]
    if report.get("schema_version") == "prover-strength.unidentified-rating.v1":
        # Absence of discordance is not absence of completed proof attempts.
        families: dict[str, dict[str, list[bool]]] = defaultdict(
            lambda: defaultdict(list)
        )
        tasks = {t["id"]: t for t in result["tasks"]}
        for row in rows:
            task = tasks[row["task"]]
            families[task["domain"]][task["family"]].append(row["status"] == "verified")
        domains = {
            d: sum(sum(v) / len(v) for v in fs.values()) / len(fs)
            for d, fs in families.items()
        }
        rating = {
            "rating": None,
            "interval95": None,
            "solve_rate_by_domain": domains,
            "balanced_solve_rate": sum(domains.values()) / len(domains),
        }
    else:
        rating = next(r for r in report["ratings"] if r["prover"] == contestant["id"])

    # Physical snapshot paths are not experiment settings. Keep all other
    # command text, executable hashes and frozen reference revisions intact.
    def command_identity(prover: dict[str, Any]) -> dict[str, Any]:
        value = dict(prover)
        value["argv"] = [
            part.replace(str(run / "product"), "$PRODUCT").replace(
                str(run / "evaluator"), "$EVALUATOR"
            )
            for part in prover["argv"]
        ]
        return value

    target = command_identity(contestant)
    target.pop("id")
    target.pop("revision")
    series = {
        "suite_id": result["suite_id"],
        "protocol": result["protocol"],
        "profile": metadata["profile"],
        "environment": metadata["environment"],
        "evaluator_tree": metadata["evaluator_tree"],
        "target_command": target,
        "reference_panel": [
            command_identity(p) for p in result["provers"] if p != contestant
        ],
        "method": report["method"],
        "prior_sd_points": report["prior_sd_points"],
    }
    return {
        "schema_version": "prover-strength.history-point.v1",
        "id": digest([metadata, receipt]),
        "series_id": digest(series),
        "series": series,
        "product_commit": metadata["product_commit"],
        "evaluator_commit": metadata["evaluator_commit"],
        "measured_at": receipt["finished_at"],
        "status": "simulated" if result["protocol"].get("synthetic") else "measured",
        "solved": sum(r["status"] == "verified" for r in rows),
        "total": len(rows),
        "outcomes": dict(Counter(r["status"] for r in rows)),
        "balanced_solve_rate": rating["balanced_solve_rate"],
        "solve_rate_by_domain": rating["solve_rate_by_domain"],
        "provisional_rating": rating["rating"],
        "rating_interval95": rating["interval95"],
        "prior_dependent": report["separation"],
        "warnings": report["warnings"],
        "effort": effort(run, rows),
        "results_sha256": receipt["results_sha256"],
    }


def record(run: Path, history: Path) -> Path:
    """Archive actual evidence without rerunning or overwriting a measurement."""
    run = run.resolve()
    point = observation(run)
    history.mkdir(parents=True, exist_ok=True)
    destination = history / point["id"]
    if destination.exists():
        if read_json(destination / "point.json") != point:
            raise ValueError("history identity collision or modified evidence")
        manifest = read_json(destination / "files.json")
        for name, expected in manifest.items():
            path = destination / name
            if not path.resolve().is_relative_to(destination.resolve()):
                raise ValueError("archive manifest escapes the observation")
            if file_sha256(str(path)) != expected:
                raise ValueError("modified archived evidence")
        return destination
    with tempfile.TemporaryDirectory(prefix=".record-", dir=history) as temporary:
        staging = Path(temporary) / "entry"
        staging.mkdir()
        for name in (
            "observation.json",
            "completed.json",
            "results.json",
            "ratings.json",
            "report.md",
        ):
            shutil.copyfile(run / name, staging / name)
        shutil.copytree(run / "artifacts", staging / "artifacts")
        if (run / "driver.py").exists():
            metadata = read_json(run / "observation.json")
            if file_sha256(str(run / "driver.py")) != metadata["driver_sha256"]:
                raise ValueError("changed measurement driver")
            shutil.copyfile(run / "driver.py", staging / "driver.py")
        (staging / "point.json").write_text(
            json.dumps(point, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        files = {
            str(p.relative_to(staging)): file_sha256(str(p))
            for p in sorted(staging.rglob("*"))
            if p.is_file()
        }
        (staging / "files.json").write_text(
            json.dumps(files, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    return destination


def points(history: Path) -> list[dict[str, Any]]:
    return sorted(
        (
            read_json(p)
            for p in history.glob("*/point.json")
            if not p.parent.name.startswith(".")
        ),
        key=lambda p: (p["measured_at"], p["id"]),
    )


def participant_registry(path: Path) -> dict[str, dict[str, str]]:
    """Map campaigns to stable public participants, never infer from settings."""
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "prover-strength.participants.v1"
        or not isinstance(value.get("participants"), list)
    ):
        raise ValueError("unsupported participant registry")
    campaigns: dict[str, dict[str, str]] = {}
    identities: set[str] = set()
    for participant in value["participants"]:
        if not isinstance(participant, dict) or any(
            not isinstance(participant.get(key), str) or not participant[key].strip()
            for key in ("id", "name")
        ):
            raise ValueError("participant requires a nonempty id and name")
        if participant["id"] in identities:
            raise ValueError("duplicate participant id")
        identities.add(participant["id"])
        assigned = participant.get("campaigns")
        if not isinstance(assigned, list) or not assigned:
            raise ValueError("participant requires campaign identities")
        for campaign in assigned:
            if not isinstance(campaign, str) or not campaign.strip():
                raise ValueError("invalid participant campaign identity")
            if campaign in campaigns:
                raise ValueError("campaign belongs to more than one participant")
            campaigns[campaign] = {
                "id": participant["id"],
                "name": participant["name"],
            }
    return campaigns


def chart_points(
    history: Path, participants: Path | None = None
) -> list[dict[str, Any]]:
    """Project immutable observations into participant histories for display.

    Protocol fingerprints remain audit metadata, not public participant identity.
    Without a registry, use the recorded contestant id unchanged.
    """
    registry = participant_registry(participants) if participants is not None else None
    data = []
    for path in history.glob("*/point.json"):
        if path.parent.name.startswith("."):
            continue
        point = read_json(path)
        if point.get("schema_version") != "prover-strength.history-point.v1":
            raise ValueError("unsupported archived history point")
        if registry is not None:
            metadata = read_json(path.with_name("observation.json"))
            campaign_metadata = metadata.get("campaign")
            campaign = (
                campaign_metadata.get("id")
                if isinstance(campaign_metadata, dict)
                else None
            )
            if not isinstance(campaign, str) or campaign not in registry:
                raise ValueError(
                    "observation campaign is absent from participant registry"
                )
            participant = registry[campaign]
        else:
            result = read_json(path.with_name("results.json"))
            matches = [
                p for p in result["provers"] if p["revision"] == point["product_commit"]
            ]
            if len(matches) != 1:
                raise ValueError("observation requires one matching participant")
            participant = {"id": matches[0]["id"], "name": matches[0]["id"]}
        data.append(
            point
            | {
                "schema_version": "prover-strength.chart-point.v1",
                "participant": participant,
            }
        )
    return sorted(data, key=lambda p: (p["measured_at"], p["id"]))


def export(
    history: Path, destination: Path, *, participants: Path | None = None
) -> None:
    """Export summaries, never execute or serve archived participant artifacts."""
    if not history.is_dir():
        raise ValueError("history directory does not exist")
    for entry in history.iterdir():
        if entry.is_symlink():
            raise ValueError("history does not admit symbolic links")
        if entry.is_dir() and not entry.name.startswith("."):
            for name, expected in read_json(entry / "files.json").items():
                path = entry / name
                if (
                    not path.resolve().is_relative_to(entry.resolve())
                    or path.is_symlink()
                ):
                    raise ValueError("archive manifest escapes its observation")
                if file_sha256(str(path)) != expected:
                    raise ValueError("modified archived evidence")
    data = chart_points(history, participants)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(
        Path(__file__).with_name("history.html"), destination / "index.html"
    )
    (destination / "history.json").write_text(
        json.dumps(data, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )


def serve(history: Path, port: int = 8765, *, participants: Path | None = None) -> None:
    """Serve only the chart and summaries on loopback, never raw worker files."""
    page = Path(__file__).with_name("history.html").read_bytes()
    # Fail before listening on invalid configuration.
    chart_points(history, participants)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/":
                body, content_type = page, "text/html; charset=utf-8"
            elif self.path == "/history.json":
                try:
                    body = json.dumps(
                        chart_points(history, participants),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode()
                except (ValueError, TypeError, KeyError, OSError):
                    self.send_error(503, "History unavailable")
                    return
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(
            f"ProverStrength history: http://127.0.0.1:{server.server_port}/",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
