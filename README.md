# ProverStrength

ProverStrength independently checks proof attempts and measures relative prover
performance under a declared task bank and resource budget. It is separate from
AgdaProver: installing it does not modify proof search or editor integrations.

[View the public strength chart](https://EgbertRijke.github.io/ProverStrength/).

## Install and evaluate

```sh
python3 -m pip install .
prover-strength check-suite suite.json --agda /absolute/path/to/agda
prover-strength run suite.json provers.json results.json \
  --agda /absolute/path/to/agda --budget 60 --environment-id my-fixed-machine-v1
prover-strength rate results.json --anchor reference-v1 \
  --output ratings.json --markdown ratings.md
```

Supply a task bank and contestant configuration as described in
[the rating protocol](prover-rating.md). The package has no Python dependencies
and imports no prover code. The command alias `agda-prover-rating` remains
available. An accepted proof counts only after independent fresh Agda checking
of the original goal.

## Budgets and failures

The wall budget includes startup, proof search and fresh final checking.
`--reference-budget` controls preliminary reference checks;
`--max-output-bytes` bounds combined stdout/stderr during execution. Larger
tasks can use larger declared budgets. Changing those settings creates a
different protocol, not a stronger score on the same scale.

Exceeding a contestant limit is recorded, not silently dropped. A checker crash
or broken evaluation setup aborts the measurement; it is not scored as a prover
failure. Missing effort counters are unknown, not zero.

This is a trusted-local POSIX runner, **not a hostile-code sandbox**. It provides
process-group wall and output supervision; competition-wide CPU, memory,
filesystem and network isolation require an external supervisor. Reference
solutions must be inaccessible to contestants in an adversarial competition.
The initial hosted campaign measures only the owner's trusted product commits.

## Ratings and commit history

The conditional Rasch/Bradley–Terry model compares which prover alone solves a
matched task. Joint successes and joint failures remain coverage data, not
relative wins. Separation is flagged and intervals are withheld; disconnected
comparisons retain outcomes without inventing a rating.

The public chart records GitHub-hosted measurements as provisional development
indicators, not a calibrated universal scale. Local measurements remain private.
Different ranking configurations form separate series. A finite task bank will
eventually saturate; it is not a claim about general mathematical strength.

The scheduled workflow checks for new first-parent product commits twice an
hour and measures at most two per batch. Delayed jobs catch up without silently
skipping intermediate commits. Existing completed observations are not rerun;
interrupted or broken evaluations remain explicitly unresolved. GitHub can delay
schedules or disable inactive repositories' schedules; manual dispatch is also
available in Actions.

Campaigns, queue receipts and immutable evidence live on the
[`results` branch](https://github.com/EgbertRijke/ProverStrength/tree/results).
Each campaign pins the evaluator, bank, participant commands and resources.
The active AgdaProver campaign uses NNUE with the weights bundled in each
measured product commit, starting at `eaabbc5`. No local training checkout or
custom model path is needed. The frozen product snapshot records the model
files and their hashes. Earlier symbolic-only measurements remain unchanged
in separate chart series; they do not measure the bundled NNUE.
Proof execution runs offline in a read-only-permission job; a separate job
publishes observations and refreshes Pages without executing archived code.

## Local history

```sh
git clone --branch results --single-branch \
  https://github.com/EgbertRijke/ProverStrength.git observations
prover-strength serve-history --history observations/history
prover-strength export-history site --history observations/history
```

Open <http://127.0.0.1:8765/> for the local chart, or host the exported static
directory. Both read existing measurements without launching proof search.
`prover-strength record PATH_TO_RUN --history observations/history` archives a
completed commit observation; `measure-pending --help` describes the bounded
local commit scheduler. `run` accepts arbitrary declared executable commands;
the initial `measure-pending` controller supports Python participants with a
`src/` layout and a frozen evaluator/reference checkout.

Campaign v1 specifies `first_commit`, `evaluator_commit`, a `suite` path and
SHA-256, `reference` and `participant` module/argument/adapter descriptions, and
an explicit `profile` of budgets and seeds. The data branch's
[`campaigns/agda-prover.json`](https://github.com/EgbertRijke/ProverStrength/blob/results/campaigns/agda-prover.json)
is the active specification. Repository paths remain local CLI inputs, not
credentials or executable downloads hidden in campaign data. Completed entries
are reused within the same campaign, toolchain and controller edition.

## Development and provenance

Feature tests, generators, experiments and historical fixtures belong in
`agda-prover-dev/prover-strength-dev/`, not the product package. Product CI checks
installation, types and lint; development CI runs the external feature tests.
Neither compiles Agda. Published rating data stays on the separate data branch.

The supplied preliminary bundle remains recoverable at commit `936d830`.
Its statistical implementation is the starting point of this product; historical
smoke output is not current or independently calibrated evidence.

Code is licensed under [GPL-3.0-or-later](LICENSE). Rasch and Bradley–Terry
methods are attributed in the protocol.
