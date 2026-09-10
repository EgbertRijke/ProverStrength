# Published ProverStrength observations

This data branch is separate from ProverStrength's product source on `main`.
It holds immutable observations, explicit measurement campaigns, and queue
receipts. The first macOS observation is preserved byte-for-byte from `d4e95ee`.
GitHub-hosted Linux observations form a separate series, not a continuation of
that machine's timing scale. These public smoke results are provisional and
not a calibrated rating of general mathematical ability.

The active campaign pins its original evaluator and task bank by commit and
checksum. Those historical commits remain available after development fixtures
are moved out of the product source. Feature tests and experimental generators
are maintained in `agda-prover-dev/prover-strength-dev/`, not here.

Queue states `started` and `harness-error` mean an unresolved evaluation, never
a proof failure. Completed measurements are not rerun by routine scheduled jobs.
An interrupted attempt requires a reviewed retry; preserve its old receipt.
Only first-parent product commits since the campaign's declared start are tracked.
GitHub schedules can be delayed; later batches catch up on pending commits.

Archived executable source is evidence only. The dashboard exports summaries;
it never executes archived files. Code provenance and GPL-3.0-or-later licensing
are preserved in the product's Git history and the accompanying LICENSE.
