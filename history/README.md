# AgdaProver strength history

Measurements start here, rather than waiting for a mature universal scale.
Each entry retains the product/evaluator commits, commands, resource profile,
source fingerprints, item-level results, accepted proofs and raw worker logs.
Existing entries are not overwritten. The live chart reads their `point.json`
files; run `prover-strength serve-history --history history` from this repository.

## First observation

Product: `d2b0d7c488b5a478fb5cc464509345b6c74c9b01`.
Evaluator: `25024ccf30f77fd661e78abe1689564b937bd9f2`.
Measured on 2026-09-10, after committing and pushing the standalone evaluator.

| Measurement | Result |
| --- | ---: |
| Provisional smoke rating | 2138.23 |
| Fixed reference rating | 1500 |
| Independently verified tasks | 11/16 (68.75%) |
| Reference tasks solved | 4/16 (25%) |
| Logic | 4/4 |
| Equality | 4/4 |
| Induction | 0/4 |
| Dependent types | 3/4 |

The fixed profile is symbolic ranking, deep search, no model overrides and a
10-second wall allowance per task including fresh final checking. The public
16-family smoke suite and Agda 2.8 checker are pinned. One worker ran offline
on an Apple M3 Max with 36 GiB RAM. Sources were copied from immutable Git
archives, site packages were disabled in workers, and before/after source
fingerprints matched. All 32 scheduled attempts are included. No product code
or benchmark was changed to obtain this score.

The five timeouts were `add-right-zero`, `add-right-succ`, `add-associativity`,
`append-right-unit` and `vector-append`. They remain recorded failures for this
profile, not conclusions that the prover cannot solve them at another budget.

The rating is a regularized development indicator. All seven discordant
outcomes favor AgdaProver, so a finite rating gap depends on the prior; there is
no meaningful finite confidence interval yet. We retain the number and its
qualification so early observations are useful without pretending calibration.

Reported effort covers 11/16 trials: 115 expanded actions and 126 verifier
calls. The five killed attempts have unknown final counters, not zero effort.
Consequently full-run proofs-per-1000-actions is unavailable for this observation.
Raw logs are preserved for improved accounting later.

See the [full report](b7529656b0eec5045e6d7e4a996497b965c81c51211ef789517caae851373e30/report.md),
[record](b7529656b0eec5045e6d7e4a996497b965c81c51211ef789517caae851373e30/point.json)
and its sibling evidence files. `files.json` fingerprints the archived evidence.
The retained driver documents this machine's exact run; its absolute paths are
provenance, not portable installation defaults.
