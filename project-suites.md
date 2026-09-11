# Source-only library tasks

The `prover-strength.project-suite.v1` bank format extends the portable,
self-contained task format with fixed Agda library context. The existing
`check-suite` and `run` commands accept it. This format provides an evaluation
boundary, not a curated task bank or a new rating formula.

## Bank contract

A bank contains:

- `schema_version`: `prover-strength.project-suite.v1`;
- `agda_version`: exactly `2.8.0` for this edition;
- `track`: the declared logical foundations, context and evaluation track;
- `contexts`: content-addressed objects, each with `files` (relative path to
  UTF-8 Agda source text) and `include_roots` (ordered relative directories);
- `tasks`: the existing `id`, `domain`, `family`, `prefix`, `starter` and
  `reference` fields, plus `context_id` and `entrypoint`.

Context IDs use `prover_strength.data.digest`: SHA-256 of sorted compact JSON,
UTF-8, without ASCII escaping or non-finite numbers. A task's entrypoint is an
ordinary `.agda` source path below an include root. It must not also occur in
the context: the original completed target module is never a worker input.
Imported files may be `.agda`, `.lagda.md`, `.lagda.tex` or `.lagda.rst` sources.
Bank preparation can convert a literate target to ordinary Agda with its native
parser while preserving the declared module and fixed context.

The prefix contains the original module, preceding context and fixed goal
signature(s), ending at a newline. It is not restricted to a module named `Task`
or a declaration named `goal`. Workers receive `prefix + starter`; reference
answers remain with the evaluator. Submitted source must preserve the prefix
exactly and complete every obligation. Whole-file tasks can keep multiple
signatures in the fixed prefix; acceptance is for the whole checked task, not
a fractional score per filled hole. A preparation pipeline must establish that
these fixed signatures encode the intended tasks; source compilation alone is
not a semantic audit of a task bank.

Paths must be canonical POSIX-relative names without traversal, dot-prefixed or
option-like components, whitespace, quotes, backslashes or control characters.
Case/Unicode-normalization collisions, file/directory collisions, interfaces,
duplicate roots and overrides of compiler-owned `Agda/` sources are rejected.
`project` is a reserved runtime field and cannot be supplied in either format.

## Checking and provenance

Each worker receives only the fixed source context, open entry and a generated
`measurement.agda-lib` containing the include roots. No other library metadata,
compiled interfaces, private audits or reference answers are copied. Source
modification or inserted symlinks cause a measurement abort. This is still the
trusted-local runner, not a hostile-code filesystem sandbox.

Reference answers and returned candidates are independently checked in new
directories with:

```text
--safe --no-libraries --no-default-libraries --ignore-all-interfaces
```

The evaluator supplies explicit `-i` roots. Source declarations retain their
own foundation options; the portable track's extra `--without-K --exact-split`
flags are not imposed on other libraries. The bank's track must distinguish
incompatible foundations. Candidate bodies cannot add imports, assumptions or
compiler pragmas. Agda, including its checks of imported sources, decides
acceptance. An invalid reference, unsupported pinned compiler, or checker crash
is a preparation/infrastructure failure, not a failed contestant proof.

The whole bank is hashed. Task fingerprints additionally bind the context ID
and entrypoint; old portable fingerprints remain unchanged. Campaign authors
must supply pinned library revisions, licenses/notices, selection criteria,
training-exposure declarations and family groupings with the bank. Keep those
as versioned campaign data, not runtime code or implicit contestant knowledge.

For AgdaProver, a library campaign can use `--no-default-agda-options` to retain
the supplied sources' foundation options, with `--ranker nnue --deep` and its
declared resource allowance. Final evaluator validation remains independent.
