# Independent tester checkpoint

Date: 2026-09-10. Product under integration test:
`d2b0d7c488b5a478fb5cc464509345b6c74c9b01`.

## Scope and boundaries

The preliminary bundle is preserved at `936d830`. Its statistical model and
fixtures are retained; the maintained implementation now lives in this
standalone repository. It imports no AgdaProver code and changes neither proof
search nor editor integrations.

Candidate reconstruction uses the public patch schema with checked Unicode edit
offsets and immutable task prefixes. Acceptance requires independent, fresh,
policy-constrained Agda checking. Process-group supervision enforces declared
wall and streaming-output budgets and cleans up descendants. Checker failures
abort a measurement instead of becoming scored prover failures. Partial results
and abort receipts are retained; existing run directories cannot be overwritten.

The checker boundary follows
[Agda 2.8's exit-code definitions](https://github.com/agda/agda/blob/v2.8.0/src/full/Agda/Interaction/ExitCode.hs):
normal typechecking rejection is distinguished from invocation/internal failure.
Suite references are subject to the same source policy as candidates.

## Verification

- 47 tests passed, including all opt-in Agda/product integration tests, with
  network denied and Python resource warnings treated as errors.
- All 32 generated reference tasks (16 families, two renamed variants) passed
  fresh Agda checking. A current-product proof passed independent validation.
- Boundary tests cover invalid edits, forged success, unresolved holes,
  nontermination, output floods, inherited/closed pipes, deadlines, descendant
  cleanup, checker crashes, and preserved failure denominators.
- Ruff lint/format checks and mypy passed. A freshly installed wheel ran the
  standalone CLI from outside the repository, without an installed product
  package or network access.

These are tester checks, not a measurement of current prover strength. The next
action after committing this checkpoint is a complete matched smoke measurement
of the current product, before implementing the chart.

## Remaining limits

This is a trusted-local POSIX evaluator, not an adversarial sandbox. Aggregate
CPU, memory and network isolation require an external supervisor. Executable
hashes are recorded, but commit measurements must additionally bind source,
models/configuration and runtime dependencies. The public smoke bank and weak
reference cannot establish a calibrated general-strength rating. Separation
and disconnected evidence must remain explicit, not be hidden by regularization.

The GitHub repository is initially private, with lightweight static/unit CI.
Historical bundle checksums describe the original snapshot, not later edits.
