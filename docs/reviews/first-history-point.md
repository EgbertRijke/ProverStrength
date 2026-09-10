# First measured history point

2026-09-10. This checkpoint follows the standalone evaluator commit `25024cc`.
Immediately after that commit/push, the fixed 16-task smoke suite was run against
immutable Git snapshots of AgdaProver `d2b0d7c` and the evaluator. No chart work
or rating-system refinement delayed the measurement.

The [archived observation](../../history/README.md) contains all 32 attempts,
15 independently accepted sources (11 product, four reference), worker logs,
commands, source inventories, toolchain/hardware/profile identities and the
original local driver. Its provisional rating is 2138.23; balanced coverage is
68.75%. Results and artifacts are fingerprinted and never silently overwritten.

## Interfaces

`record` archives an existing completed observation without rerunning search.
It checks result/report identity, source-integrity receipts and accepted proof
hashes. Repeat recording is idempotent and rejects modified archived evidence.
The history series identity keeps the frozen reference panel, evaluator,
protocol, environment and command settings; only physical snapshot paths and
the measured product revision are abstracted for cross-commit comparison.

`serve-history` exposes only the chart and its summaries on loopback. It serves
no raw worker files and uses no external scripts or fonts. The chart refreshes
every ten seconds, separates incompatible series and labels prior-dependent
ratings. No historical points are fabricated. This is not yet an automatic
measurement watcher or a public Pages deployment.

Effort reports count unsuccessful attempts when available and retain missing
counter coverage. The five external timeouts did not yield final counters, so
full-run proofs/action and CPU metrics are unavailable rather than misleadingly
calculated from successful trials only. Counter telemetry remains self-reported,
not a cross-prover unit of work.

## Checks

- 56 unit/integration tests pass, including all real Agda/product tests with
  network denied and resource warnings treated as errors.
- Ruff formatting/lint and mypy pass; inline JavaScript passes Node's syntax
  check. The installed wheel includes the chart and new CLI commands.
- HTTP checks return the first real observation, no-store headers and the
  chart; unrelated/raw-file routes return 404. No browser backend was available
  for visual testing, so a visual rendering pass is not claimed.
- The completed measurement was archived and read back; its checked proof
  hashes and recorded result/report hashes match. Frozen source inventories
  remain unchanged. No solver code or benchmark was modified.

Next priority is practical measurement automation, not improving the scale
before collecting more points. Public Pages/Actions hosting is a feasible
recommendation under discussion; no repository visibility change or measurement
workflow has been enabled at this checkpoint.
