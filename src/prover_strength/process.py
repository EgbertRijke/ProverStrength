"""Bounded local POSIX execution, not a hostile-code sandbox."""

from __future__ import annotations

import math
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

MAX_OUTPUT = 16 * 1024 * 1024


class HarnessError(RuntimeError):
    """An evaluator failure aborts a run rather than creating a scored loss."""


class OutputLimitError(RuntimeError):
    """A process exceeded its declared combined stdout/stderr allowance."""


def process(
    argv: list[str],
    cwd: Path,
    seconds: float,
    *,
    seed: int = 0,
    max_output: int = MAX_OUTPUT,
) -> tuple[int, str, str]:
    if isinstance(seconds, bool) or not math.isfinite(seconds):
        raise ValueError("wall budget must be finite")
    if seconds <= 0:
        raise TimeoutError("task wall budget exhausted")
    if type(max_output) is not int or max_output <= 0:
        raise ValueError("output budget must be a positive integer")
    if os.name != "posix":
        raise HarnessError("local process-group supervision requires POSIX")
    deadline = time.monotonic() + seconds
    try:
        child = subprocess.Popen(
            argv,
            cwd=cwd,
            env=dict(os.environ, PPR_SEED=str(seed)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        raise HarnessError(str(error)) from error
    buffers = [bytearray(), bytearray()]
    total = 0
    assert child.stdout is not None and child.stderr is not None
    try:
        with selectors.DefaultSelector() as poller:
            for index, stream in enumerate((child.stdout, child.stderr)):
                os.set_blocking(stream.fileno(), False)
                poller.register(stream, selectors.EVENT_READ, index)
            while poller.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("task wall budget exhausted")
                for key, _ in poller.select(min(remaining, 0.05)):
                    chunk = os.read(key.fd, min(65536, max_output - total + 1))
                    if not chunk:
                        poller.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > max_output:
                        raise OutputLimitError(
                            f"combined process output exceeded {max_output} bytes"
                        )
                    buffers[key.data].extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("task wall budget exhausted")
            try:
                child.wait(timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError("task wall budget exhausted") from error
        return (
            child.returncode,
            buffers[0].decode("utf-8", errors="replace"),
            buffers[1].decode("utf-8", errors="replace"),
        )
    finally:
        # Includes cancellation and descendants that outlive their direct parent.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
        child.stdout.close()
        child.stderr.close()
