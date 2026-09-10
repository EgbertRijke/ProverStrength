# ProverStrength

ProverStrength independently checks proof attempts and measures relative prover
performance under a declared task bank and resource budget. It is separate from
AgdaProver: installing it does not modify proof search or editor integrations.

## Install and try it

```sh
python3 -m pip install .
prover-strength demo runs/demo --bootstrap 100
prover-strength generate runs/smoke.json --variants 1 --seed 42
prover-strength check-suite runs/smoke.json --agda /absolute/path/to/agda
```

The demo is simulated. The generated 16-family suite is public development smoke
coverage, not a calibrated test of general mathematical strength. An accepted
proof counts only after independent fresh Agda checking of the original goal.

See [the rating protocol](prover-rating.md) for contestant JSON, paired runs and
the statistical model. Its `agda-prover-rating` commands remain available as an
alias for `prover-strength`; applying its historical product patch is unnecessary.
The standalone package has no Python dependencies and imports no product code.

## Budgets and failures

The wall budget includes startup, proof search and fresh final checking. A run
can declare larger budgets for harder tasks and larger proof outputs:

```sh
prover-strength run runs/smoke.json provers.json runs/results.json \
  --agda /absolute/path/to/agda --budget 300 --reference-budget 300 \
  --max-output-bytes 67108864 --environment-id my-fixed-machine-profile
```

`--reference-budget` controls preliminary reference checks; `--max-output-bytes`
limits combined stdout/stderr per process during execution. Exceeding a
contestant limit is recorded, not silently dropped. A checker crash or broken
evaluation setup aborts the measurement; it is not scored as a prover failure.
Changing resource settings creates a different protocol, not a stronger score
on the same scale.

This is a trusted-local POSIX runner with bounded output and process-group wall
supervision. It is **not a hostile-code sandbox** and does not enforce aggregate
CPU, memory or network quotas. Competition use requires external isolation.
Reference solutions must remain inaccessible to contestants in that environment.

## Ratings and commit history

The supplied conditional Rasch/Bradley–Terry model compares which prover alone
solves a matched task. Both successes and both failures remain coverage data,
not relative wins. A perfect record against a weak baseline does not establish a
finite strength gap: separation is flagged and intervals are withheld. A finite
bank cannot measure arbitrarily strong provers without eventually saturating.

A live history keyed to exact AgdaProver commits is the next implementation
checkpoint. It will retain solve rates and unmeasurable-rating states rather
than drawing misleading finite scores, and keep incompatible protocols separate.
See [the bounded implementation plan](PLAN.md).

## Tests and provenance

```sh
python -W error::ResourceWarning -m unittest discover -s tests -v
PPR_TEST_AGDA=/absolute/path/to/agda \
  PPR_TEST_PROVER=/absolute/path/to/agda-prover \
  python -W error::ResourceWarning -m unittest discover -s tests -v
```

Ordinary CI runs no Agda build. Real checker/adapter tests are explicitly enabled
with the variables above. Run every candidate under the same declared conditions.

The original bundle, examples and validation receipts are preserved at commit
`936d830`; root `SHA256SUMS` describes that historical snapshot, not subsequent
README or implementation changes. The patch is retained as provenance only.
Its statistical implementation and tests form this package's starting point;
new work hardens execution and establishes maintained measurement interfaces.
Historical smoke results are not current or independently calibrated ratings.

Code is licensed under [GPL-3.0-or-later](LICENSE). The rating model builds on
Rasch and Bradley–Terry methods, as attributed in the protocol.
