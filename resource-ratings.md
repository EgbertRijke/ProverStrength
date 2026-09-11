# Resource-sensitive completion ratings

This edition measures how much of a declared resource range is sufficient for
verified completion. It credits faster common successes, unlike the original
single-cutoff conditional rating. It is a bounded performance index, **not an
Elo scale**, a universal difficulty estimate or a count of filled holes.

## Freeze the measurement

Use `prover-strength.resource-profile.v1` with explicit positive lower/upper
bounds. `elapsed_seconds` is mandatory and primary; effort axes are optional.
For example (illustrative values, not an implicit campaign):

```json
{
  "schema_version": "prover-strength.resource-profile.v1",
  "ranges": {
    "elapsed_seconds": [0.1, 60],
    "actions_expanded": [1, 8000],
    "verifier_calls": [1, 20000]
  },
  "effort_accounting": "agdaprover.p0.v1-self-reported"
}
```

Pass the profile to `run --resource-profile profile.json` before execution. It
joins the immutable protocol and must match when results are combined or scored.
The time upper bound cannot exceed the run's wall allowance. The profile does
not silently alter the contestant's search budgets; commands and all other
resource limits remain frozen separately. Use the same task/seed schedule and
conditions for compared provers, with NNUE enabled unless the experiment is an
explicit ablation.

`resource-rate ... --profile profile.json --output report.json` emits JSON;
`--markdown report.md` adds a readable report. `--reference ID` adds paired
comparisons, not a fixed artificial rating anchor. Without a reference, one
prover can still be measured. `--retrospective` permits analysis of old results
without a pre-recorded profile and labels that fact; it cannot override a
different recorded profile or turn a retrospective analysis into preregistration.

## Score and curves

For each axis with range `[L, U]`, the trial's contribution is:

```text
0                                                  if not verified
clamp((log U - log(max(L, cost))) / (log U - log L)) if verified
```

`clamp` restricts the result to `[0, 1]`. This is exactly the normalized area
under that trial's completion-by-consumed-resource curve on a logarithmic
resource axis. Every declared trial remains in the denominator. A verified
completion at or below `L` receives 1, at or above `U` receives 0. Completion
at exactly the upper endpoint still appears in the separately reported solve
rate and curve. Faster completion improves the score inside the range, even
when both provers solve exactly the same tasks. Quick failed attempts never
receive completion credit.

Average within each task family over tasks and seeds, then equally over
families within each domain, then equally over domains. Multiply by 100 for a
0–100 rating. Repeated seeds and renamed variants do not become independent
families. Report each resource axis independently; seconds, actions and checker
calls are not summed or assigned an arbitrary exchange rate. Changing the bank,
weights, foundations, conditions, accounting or ranges changes the edition.

These are curves from the recorded run, not predictions of how a budget-aware
solver would behave if restarted with different limits. Unfinished runs show no
verified completion in that run; the score does not infer eventual impossibility
or fabricate a completion time after censoring. Whole-file trials require a
verified whole file. Partial paths or filled-hole fractions are diagnostics only.

## Effort and uncertainty

New runner records carry optional `prover-strength.effort.v1` evidence with an
`accounting` identifier and nullable nonnegative integer `actions_expanded` and
`verifier_calls`. AgdaProver's adapter extracts these from its versioned result;
generic candidate-JSON adapters may supply this record in `effort`. Invalid or
unavailable self-reports remain unknown and never confer proof acceptance.
The runner also records its own `evaluator_checks` separately. Solver checker
counts do not include these additional independent checks or reference-bank
preparation. End-to-end wall time includes trial setup and independent checking.

Counters from incompatible accounting schemes are not compared. Missing effort
on a verified trial gives an interval of possible contribution `[0, 1]`, not a
zero. Its axis rating/curve is withheld where incomplete, with explicit bounds.
An unsuccessful trial has zero completion contribution even if its work count
is unknown. Total effort still includes failed attempts and is unavailable if
any count is missing; observed partial totals and coverage are always shown.
Self-reported counters are useful within a compatible prover/instrumentation
family, not hardware-independent or adversarially trustworthy units of work.

Paired reports include completion gains/losses, score differences and geometric
reference/candidate cost factors on common verified trials with known positive
costs. Factors greater than 1 favor the candidate. This selected-subset diagnostic
never replaces the all-trial rating and coverage; zero/unknown costs are counted
explicitly rather than divided or imputed.

Bootstrap whole families within each domain with the same draw for all provers
and axes. Report paired differences from these paired draws. Intervals require
at least 100 draws and two families in every domain; smaller samples retain point
estimates and explicit warnings. Even available intervals describe sampling of
the declared families, not unseen domains or wall-clock noise from one run.
Hardware noise needs repeated matched trials. Preserve every original observation
and label small or retrospective studies. Historical single-cutoff ratings are
not silently recomputed, and the hosted chart changes only with an explicitly
versioned campaign migration.
