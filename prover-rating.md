# Portable prover rating

Portable Prover Rating (PPR) measures the relative ability of automatic provers
to produce accepted proofs within a fixed resource budget. It uses an Elo-like
scale with an immutable reference prover assigned 1500 points. The reference
is a convention, not a claim that the prover equals a chess player rated 1500.

The maintained implementation is the standalone `prover-strength` package in
this repository; no patch to AgdaProver is required. The original implementation
bundle and measurements remain preserved at commit `936d830`.

The implementation has no third-party Python dependencies. The rating engine
accepts results from any conforming evaluator; the included runner evaluates
Agda tasks and understands AgdaProver's current JSON reconstruction interface.

## What library independence means

The **portable track** requires each task to contain its entire context,
definitions, allowed lemmas, and goal. No external mathematical library may be
imported or searched. A contestant may supply its own implementation and trained
weights, but runtime access to additional theorem databases belongs in a separate
track. The evaluator checks proofs against the supplied context only.

Consequently, these measurements do not require agda-unimath, the Agda standard
library, or a particular library's naming and organization. They still depend on
the specified logic, task distribution, representation, and budget. There is no
distribution-free total ordering: a prover specializing in arithmetic can beat
another on arithmetic and lose on dependent types. A rating formula cannot
remove this fact. Cross-assistant comparisons require audited, equivalent
encodings in a shared logical fragment; the supplied adapter only covers Agda.

The Agda track uses intensional type theory with `--without-K --exact-split`.
Completed sources must pass `--safe`. Results for cubical reasoning, classical
axioms, different type theories, library retrieval, and different resource
budgets must have different track or protocol identifiers.

## The rating model

This is the original, single-cutoff rating edition. It does **not** credit a
faster completion when both contestants finish within the cutoff. Runtime,
search actions and checker calls are retained evidence, but do not currently
enter this fitted score. The separate [resource-sensitive completion report](resource-ratings.md)
now credits those differences through explicitly declared resource ranges and
independent effort axes. It is a bounded index, not this Elo-like fitted model.
Historical ratings keep their original meaning and will not be silently changed;
the hosted campaign has not yet migrated.

Every contestant attempts the same tasks under the same protocol. For task
variant and trial t, set X_pt = 1 exactly when prover p's completed artifact is
independently accepted within budget, and 0 otherwise.

For a pair A, B, the four outcomes are:

| A | B | Rating evidence |
| --- | --- | --- |
| Solves | Fails | A wins a discordant comparison |
| Fails | Solves | B wins a discordant comparison |
| Solves | Solves | No relative evidence; record both successes |
| Fails | Fails | No relative evidence; record both failures |

Do not turn all common successes and failures into ordinary Elo draws. That
would make the apparent strength gap depend strongly on how many trivial or
unreachable tasks were included. Always publish balanced solve rates as well:
the relative rating alone cannot describe coverage or collective progress.

The model is

    P(A solves | exactly one of A, B solves t)
      = 1 / (1 + 10^((R_B - R_A) / 400)).

Thus +400 means 10:1 odds of being the sole solver **conditional on a
discordance**. It does not mean a 90.9% chance of solving a random theorem.

The connection to item difficulty is explicit. In a Rasch model,

    P(X_pt = 1) = logistic(theta_p - beta_t),
    R_p = 1500 + (400 / ln 10) theta_p.

If the two responses are conditionally independent given their abilities and
the task difficulty, then

    P(X_At = 1, X_Bt = 0) / P(X_At = 0, X_Bt = 1)
      = exp(theta_A - theta_B).

The nuisance parameter beta_t cancels. This is **model-conditional** difficulty
invariance, not a proof that real provers satisfy Rasch assumptions. Even
deterministic provers can be measured by sampling tasks; repeated identical
deterministic executions do not create independent evidence. Shared algorithms,
specialization, and presentation effects can violate the model. Inspect the
reported pairwise observed/predicted discordance fractions and domain solve
rates; use separate domain ratings when the scalar summary conceals differences.

This uses the established Rasch/Bradley–Terry mathematical model, not a new
statistical discovery. The proposal is the evaluation protocol and implementation.
See [Lan, Chiang and Studer, *An Estimation and Analysis Framework for the Rasch
Model*](https://arxiv.org/abs/1806.03551) and [Tang, Wang and Jin, *Is Elo Rating
Reliable? A Study Under Model Misspecification*](https://arxiv.org/abs/2502.10985).

### Balancing and fitting

A **family** groups correlated problems: all renamed variants, parameter
instances of one generator template, related lemmas, or tasks extracted from
one tightly coupled proof development. Changing a family label does not make
evidence independent; family assignments require review.

Let D be the number of domains, F the total number of families, F_d the number
in domain d, V_f the number of variants in family f, S the number of declared
trials, and P the number of contestants. Each discordant pair receives weight

    w_t = F / (D F_d V_f S (P - 1)).

Each domain receives equal total task weight and each family receives equal
weight within its domain. Variants and repetitions divide a family's weight;
copying a family member does not create another independent family. The
1/(P−1) factor prevents quadratic pair expansion from setting the regularization
strength merely through the number of opponents. Induced pairs remain
dependent; the bootstrap handles them together.

With theta_reference = 0, minimize

    sum_discordances w_t [log(1 + exp(theta_A - theta_B))
                          - y_t (theta_A - theta_B)]
      + (1 / (2 sigma^2)) sum_(p != reference) theta_p^2,

where y_t = 1 for an A-only success, sigma = 800 ln(10)/400 by default.
The Gaussian penalty is centered on the fixed reference. Strict convexity
gives a unique finite optimum. Batch fitting avoids the arbitrary game order
and learning-rate choices of sequential Elo updates. Ratings are not integers
internally; rounding is only for display.

The implementation checks the undirected graph of observed discordances.
If disconnected, there is no empirical common scale and it refuses to produce
a ranking, even though a prior could invent one. It separately checks strong
connectivity of the directed win graph. Complete or quasi separation makes
finite magnitudes prior-dependent: the report flags this, withholds intervals,
and shows the maximum rating shift when the prior SD is doubled.

The regularized composite fit can move when the contestant panel changes,
especially under misspecification. Keep a declared panel of diverse reference
systems and record every contestant revision. Comparisons across reports require
matching protocol and scale conventions; do not treat separately fitted ratings
from different task banks as interchangeable simply because both have a 1500
anchor. Establish a new edition, or validate linking on a broad shared anchor
panel before publishing a cross-edition trend. Automatic bank equating is not
implemented.

### Uncertainty

The runner's results form a complete panel. The rating engine resamples entire
families **within each domain**, preserving all variants, trials, and pairwise
outcomes in a sampled family, then refits. It reports percentile 95% intervals
for ratings and paired rating differences. These quantify family-sampling
variability of the regularized estimate, not a Bayesian posterior or a guarantee
of nominal coverage under misspecification. The fixed anchor has no estimated
uncertainty because it defines the origin.

Intervals are withheld for fewer than 100 bootstrap draws, separated data, or
any disconnected bootstrap graph. Disconnected draws are never silently
discarded. Samples with fewer than 30 families or fewer than five in a domain
are marked provisional. These thresholds are conservative reporting rules,
not sample-size theorems. More draws improve Monte Carlo precision, not the
amount of evidence. Use 1000 or more for a publication and inspect stability.

## Evaluation protocol

1. **Freeze the track and artifacts.** Record compiler/kernel version and hash,
   prover commit, executable/model hashes, command, premise policy, hardware,
   thread/GPU allocations, cache policy, and time/memory quotas. Prover search
   nodes and verifier-call counts are useful diagnostics but are not portable
   computational units. Use fixed hardware and externally enforced resources;
   publish separate ratings for, for example, 10, 60, and 300 seconds.
2. **Freeze sampling before seeing outcomes.** Choose domains and family weights,
   deduplicate semantic near-copies, and check that every task is well formed
   and provable under its declared assumptions. Keep the same task/variant/seed
   schedule for every contestant. Unsupported in-track tasks count as failures;
   a different supported logic calls for a different track.
3. **Prevent leakage.** Freeze model training before releasing held-out tasks;
   split by proof development and generator template, not by renamed copies.
   Include several presentations of the same mathematics, fresh generated
   instances, and curated self-contained problems from diverse origins. Renaming
   alone is not a defense against memorization. Keep reference proofs out of the
   contestant environment and release held-out proofs only after the evaluation.
4. **Run automatically.** Randomize and interleave the matched schedule; count
   parsing, premise processing, search, retries, model calls, and final checking
   against the same wall budget. Declare whether initial process/model loading
   is included. The supplied runner includes it. Restart per task; no learning
   or proof reuse across tasks. For stochastic systems, prescribe seeds and
   repetitions in advance. Do not report the best of several undeclared attempts.
5. **Verify the whole task.** Restore the immutable original goal/context in a
   fresh checking environment; reject altered assumptions, unfinished goals,
   unapproved imports, unsafe pragmas, and invalid proofs. A prover's own
   `verified` flag is not proof authority. For this Agda track, use a fresh
   directory, no libraries, no reused interfaces, and `--safe`. Agda's
   [safe-mode restrictions](https://agda.readthedocs.io/en/v2.8.0/language/safe-agda.html)
   and [library flags](https://agda.readthedocs.io/en/v2.8.0/tools/command-line-options.html)
   supply the kernel-side checks.
6. **Keep every outcome.** Unsolved, timeout, resource exhaustion, invalid proof, crash, and unsupported
   task score zero. A broken evaluator or missing compiler aborts the run and
   requires repair; it is not an observation to omit selectively. Archive raw
   output, accepted source, hashes, and completed-trial logs.
7. **Publish scope with the score.** Report edition, track, budget, reference
   revision, family count, intervals, balanced/domain solve rates, and fit
   diagnostics. Investigate large pairwise residuals and domain reversals before
   using a single leaderboard. Hold out complete families for predictive checks.

Competition practice already uses separate logical divisions, controlled
resources, similarity-aware sampling, obfuscation, and solution requirements;
see the [CASC design](https://tptp.org/CASC/J12/Design.html). PPR adds a paired,
family-balanced relative scale and explicit uncertainty to that general pattern.

## Run it

Install this standalone checkout with `python3 -m pip install .`.

```sh
# Supply a bank conforming to portable-prover-rating.suite.v1.
agda-prover-rating check-suite suite.json --agda /absolute/path/to/agda
```

The public smoke suite exercises the harness, not the full range of mathematical
proof search. It includes implication reasoning, equality, induction on numbers
and lists, dependent pairs, and indexed vectors. It has too few independent
families for a mature rating, its reference proofs are public, and new renamings
do not fix those limitations. Use it for development, not a claim of general
prover strength.

Create `provers.json`, replacing commands and revision strings with the exact
artifacts being evaluated. Use absolute paths if the executable is not on PATH:

```json
[
  {
    "id": "reference-v1",
    "revision": "REPLACE-WITH-EXACT-REFERENCE-COMMIT",
    "adapter": "candidate-json",
    "argv": ["/absolute/path/to/reference-worker", "{source}",
             "--agda", "{agda}", "--budget", "{budget}"]
  },
  {
    "id": "AgdaProver-candidate",
    "revision": "REPLACE-WITH-EXACT-COMMIT-AND-CONFIGURATION",
    "adapter": "agdaprover",
    "argv": ["agda-prover", "prove-prefix", "{source}",
             "--agda", "{agda}", "--timeout", "{budget}", "--deep"]
  }
]
```

The original smoke reference tried only four lambda expressions and remains
pinned in the historical campaign. It is not a bundled product command.
A contest should register an immutable capable reference and a diverse panel;
the reference should neither fail nor solve almost everything on its bank. The adapter reads the existing
AgdaProver reconstruction contract and does not change proof search.

```sh
agda-prover-rating run suite.json provers.json run.json \
  --agda /absolute/path/to/agda --budget 60 \
  --environment-id machine-and-resource-profile-v1

agda-prover-rating rate run.json --anchor reference-v1 \
  --output ratings.json --markdown ratings.md

# Same protocol/suite/seeds, disjoint contestants, each fully evaluated:
agda-prover-rating rate reference-run.json candidate-run.json \
  --anchor reference-v1 --output comparison.json --bootstrap 1000

# A separate domain score; fails explicitly if it lacks connecting evidence.
agda-prover-rating rate run.json --domain induction \
  --anchor reference-v1 --output induction-ratings.json
```

Default executions have one trial per task. Pass `--seeds 1 2 3` for a
prespecified repeated design; the generic worker receives the seed in
`PPR_SEED` and can also receive `{seed}` in its arguments. AgdaProver has no seed
argument in the inspected CLI, so its repeated deterministic runs add no new
search diversity. Result files cannot mix budgets, suites, environments,
compiler identities, task manifests, or seed schedules. Missing and duplicate
observations are rejected.

The local POSIX runner enforces a wall deadline on the worker's process group
and includes final fresh checking in that deadline. It bounds combined stdout
and stderr during execution, not after potentially unlimited file growth.
`--max-output-bytes` defaults to 16 MiB per process and can be increased for
larger artifacts. Preliminary reference checking has a separate explicit
`--reference-budget` (default 60 seconds). Both settings are recorded in the
protocol; changing them requires a separate comparison series. It runs one worker at a
time. It **does not implement a hostile-code sandbox or aggregate memory, GPU,
CPU, and network quotas**. Supply those using a controlled external supervisor
for competition measurements, and identify the profile in `environment_id`.
New output is marked `local-wall-stream-bounded-process-group-v2`; historical
v1 results are not silently merged with it. An evaluator cannot infer resource
equality from an arbitrary profile name. Checker and contestant executable files
are hashed and checked for mutation, but toolchain data, model files,
interpreter-loaded source and dependencies must also be pinned
in the evaluation image. This runner's metadata alone is not a full attestation.

The run writes an adjacent `.artifacts` directory with worker/checker logs,
accepted sources, and an append-only completed-trial log. It refuses to reuse
that directory. It does not resume interrupted runs automatically. Backend
errors are recorded as failed attempts; fix configuration errors discovered in
smoke testing before freezing a contest. Evaluation harness failures abort.

## Other provers and task banks

The generic `candidate-json` adapter accepts one JSON object on stdout:

```json
{"candidate": "THE COMPLETE Task.agda SOURCE"}
```

Use `{"candidate": null}` when unsuccessful. The candidate must preserve the
task's entire `prefix` exactly, including the final `goal` signature. Its
remaining text can supply clauses and helper definitions. The runner performs
the final acceptance check. The worker is started with an argv array, never a
shell command; `{source}`, `{budget}`, `{agda}`, and `{seed}` are substituted.

To add tasks, follow the JSON produced by `generate`. Each task has a globally
unique `id`, `domain`, `family`, immutable `prefix`, unfinished `starter`, and
private completed `reference` body. The portable Agda adapter intentionally
requires `module Task where`, the fixed header, and one final `goal` signature.
Trusted context may register its self-contained equality with `BUILTIN EQUALITY`.
All reference bodies are checked before scoring begins. Multi-hole work can
occur inside the final declaration; benchmark interfaces for larger mutually
dependent declaration blocks need a separate adapter and reviewed preservation
rules. Do not weaken the prefix check to admit arbitrary file modifications.

A non-Agda evaluator can emit `portable-prover-rating.results.v1` directly.
The archived development `simulated-results.json` is a schema example, not a product fixture; the authoritative field
validation is in `prover_strength.data.validate`. Include task/family/domain
identities and fingerprints, the full protocol, exact contestant revisions,
declared seeds, and one row per contestant/task/seed. Successful rows require
`checker_accepted: true`, `artifact_sha256`, and an elapsed time within budget.
The rating engine trusts these evaluator records; it does not authenticate a
JSON boolean or recheck arbitrary proof formats. Only a trusted evaluator can
certify that an imported result is sound. Simulation is marked in its protocol
and cannot be merged with real measurements.

The JSON report includes paired rating-difference intervals and observed versus
predicted pairwise fractions; the Markdown report provides the smaller human
summary. Always retain the underlying results, which are fingerprinted in the
report. There is no valid numerical rating for an unmeasured AgdaProver release.
Its `scale_id` fingerprints the model version, suite, protocol, prior, and
reference descriptor. Equal scale identifiers are necessary for direct scale
comparison; the full input fingerprint also identifies the contestant panel.
