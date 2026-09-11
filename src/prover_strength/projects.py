"""Immutable source-only library contexts for independently checked tasks.

The evaluator accepts data, never a contestant's imports or build commands.
Reference answers remain in the controller; workers receive only fixed context
and the open entry. Corpus selection and provenance review belong upstream.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from .data import digest, identifier

SCHEMA = "prover-strength.project-suite.v1"
FLAGS = [
    "--safe",
    "--no-libraries",
    "--no-default-libraries",
    "--ignore-all-interfaces",
]
SOURCE_SUFFIXES = (".agda", ".lagda.md", ".lagda.tex", ".lagda.rst")
MANIFEST = "measurement.agda-lib"


def relative_path(value: object, *, directory: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("project path must be nonempty POSIX-relative text")
    if directory and value == ".":
        return value
    parts = value.split("/")
    if (
        any(
            not part
            or part.startswith((".", "-"))
            or any(c.isspace() or ord(c) < 32 or c in "\"'" for c in part)
            for part in parts
        )
        or str(PurePosixPath(value)) != value
    ):
        raise ValueError("project path has unsafe or noncanonical components")
    return value


def validate_context(context: object) -> dict[str, Any]:
    if not isinstance(context, dict) or set(context) != {"files", "include_roots"}:
        raise ValueError("project context requires files and include roots")
    files, roots = context["files"], context["include_roots"]
    if not isinstance(files, dict) or not isinstance(roots, list) or not roots:
        raise ValueError("invalid project context files/include roots")
    spellings: dict[str, str] = {}
    for name, source in files.items():
        relative_path(name)
        if not name.endswith(SOURCE_SUFFIXES) or not isinstance(source, str):
            raise ValueError("project context admits only Agda source text")
        if "\0" in source:
            raise ValueError("NUL in project source")
        parts = name.split("/")
        for length in range(1, len(parts) + 1):
            ancestor = "/".join(parts[:length])
            key = unicodedata.normalize("NFC", ancestor).casefold()
            if spellings.setdefault(key, ancestor) != ancestor:
                raise ValueError("case/normalization-colliding project paths")
        if any("/".join(parts[:n]) in files for n in range(1, len(parts))):
            raise ValueError("project source is another source's directory")
    for root in roots:
        relative_path(root, directory=True)
    if len(set(roots)) != len(roots):
        raise ValueError("duplicate project include root")
    return context


def bind_tasks(suite: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve hash-pinned shared contexts without mutating the saved bank."""
    if any("project" in task for task in suite["tasks"]):
        raise ValueError("task contains a reserved runtime field")
    if suite.get("schema_version") != SCHEMA:
        return suite["tasks"]
    if suite.get("agda_version") != "2.8.0":
        raise ValueError("project bank currently requires Agda 2.8.0")
    contexts = suite.get("contexts")
    if not isinstance(contexts, dict):
        raise ValueError("project bank needs content-addressed contexts")
    for identity, context in contexts.items():
        validate_context(context)
        if identity != digest(context):
            raise ValueError("project context checksum mismatch")
    result = []
    for task in suite["tasks"]:
        entry = relative_path(task.get("entrypoint"))
        if not entry.endswith(".agda"):
            raise ValueError("project entrypoint must be ordinary Agda source")
        context_id = task.get("context_id")
        if not isinstance(context_id, str) or context_id not in contexts:
            raise ValueError("project task references an unknown context")
        context = contexts[context_id]
        # Include the entry in collision and file/directory checks.
        if entry in context["files"]:
            raise ValueError("project context contains the target's original file")
        validate_context({**context, "files": {**context["files"], entry: ""}})
        for root in context["include_roots"]:
            base = "" if root == "." else root + "/"
            if any(
                name.startswith(base + "Agda/") for name in (*context["files"], entry)
            ):
                raise ValueError("project cannot shadow Agda runtime sources")
        if not any(
            root == "." or entry.startswith(root + "/")
            for root in context["include_roots"]
        ):
            raise ValueError("project entrypoint is outside all include roots")
        for key in ("prefix", "starter", "reference"):
            identifier(task[key], key)
        if not task["prefix"].endswith("\n"):
            raise ValueError("project fixed prefix must end at a line boundary")
        result.append({**task, "project": context})
    return result


def fixed_files(task: dict[str, Any], source: str) -> dict[str, str]:
    context = task["project"]
    return {
        **context["files"],
        task["entrypoint"]: source,
        MANIFEST: "include: " + " ".join(context["include_roots"]) + "\n",
    }


def materialize(task: dict[str, Any], source: str, root: Path) -> Path:
    for name, text in fixed_files(task, source).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / task["entrypoint"]


def unchanged(task: dict[str, Any], source: str, root: Path) -> bool:
    for name, text in fixed_files(task, source).items():
        path = root / name
        # Inspect only the task's path components. Trusted temporary roots can
        # themselves live below a platform alias such as macOS's /var symlink.
        parts = Path(name).parts
        if (
            any(
                root.joinpath(*parts[:length]).is_symlink()
                for length in range(1, len(parts) + 1)
            )
            or not path.is_file()
        ):
            return False
        expected = text.encode("utf-8")
        try:
            with path.open("rb") as stream:
                if stream.read(len(expected) + 1) != expected:
                    return False
        except OSError:
            return False
    return True


def checker_arguments(task: dict[str, Any], root: Path) -> list[str]:
    return [
        *FLAGS,
        *(
            arg
            for path in task["project"]["include_roots"]
            for arg in ("-i", str(root / path))
        ),
        task["entrypoint"],
    ]
