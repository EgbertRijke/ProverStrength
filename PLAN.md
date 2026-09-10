# ProverStrength implementation plan

The original supplied bundle is preserved at commit `936d830`. Keep evaluation,
statistics and charts here, outside AgdaProver's production package. The first
scope is a working local development-strength history, not a calibrated universal
rating or a public competition service.

## First checkpoint: independent execution — complete

Completed and locally verified on 2026-09-10; see the
[checkpoint review](docs/reviews/standalone-tester.md).

- Extract the existing rating implementation into a standalone package without
  importing or patching the product. Preserve the original bundle and evidence.
- Pin the reconstruction adapter to its public schema; freshly check the exact
  immutable task, never trust a contestant's success flag.
- Supervise output and deadlines during execution, clean up child processes,
  and distinguish checker/infrastructure failure from an invalid candidate.
- Make reference-checking and output budgets explicit and recorded, so larger
  proofs can use a different declared protocol instead of a hidden tester limit.
- Keep independent baseline/math/schema checks and small opt-in Agda integration
  tests. No whole-library runs or product search changes.

## Second checkpoint: measured commit history

Immediately after the first checkpoint's commit, measure the current product
against the frozen smoke suite and reference baseline. Start accumulating real
observations now; chart sophistication and stronger anchors must not delay this.

- Record real runs against immutable product commits and an immutable reference
  panel. Bind suite, toolchain, model/configuration, hardware and resource profile.
- Append complete observations without overwriting previous outcomes. Display
  missing/failed measurements explicitly and separate incompatible editions.
- Provide a local auto-refreshing chart. Show balanced and domain solve rates;
  withhold empirical rating points when saturation/separation or disconnected
  evidence makes their magnitude unidentifiable. Do not invent historical scores.
- Add an external watcher/queue for subsequent commits without coupling product
  commits or normal CI to expensive measurement. Freeze a small default suite.

## Later qualification

After the local pipeline works, review a broader difficulty range and stronger
anchors. A finite smoke bank cannot measure arbitrarily strong provers; saturation
requires a new, explicitly linked edition, not a silent change of scale. Do not
claim calibrated strength from the public 16-family demonstration.

At each checkpoint, run focused tests, inspect the full diff, update evidence,
commit and push when a remote is configured, then choose the next practical task.
The user authorized `EgbertRijke/ProverStrength` on GitHub. Use the configured
`upstream` remote, initially private, and lightweight CI without routine Agda
builds. Do not wait for hosted CI before continuing after a locally tested push.

The user also approved supplementary within-prover action-efficiency reporting:
include failed-search effort, unknown-counter coverage, verifier calls and
available CPU accounting. Keep this separate from cross-prover ratings; actions
are neither universally comparable nor interchangeable with kernel work.
