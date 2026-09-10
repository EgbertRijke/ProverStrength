# Portable Prover Rating

This bundle contains an implementation patch for AgdaProver, the complete rating
protocol, a synthetic statistical demonstration, and real development smoke-test
results with proof artifacts and logs. No third-party Python dependencies are added.

Base repository: https://github.com/EgbertRijke/agda-prover
Base commit: d2b0d7c488b5a478fb5cc464509345b6c74c9b01

## Install

From that AgdaProver checkout, with this bundle unpacked elsewhere:

```sh
git apply --check /path/to/portable-prover-rating.patch
git apply /path/to/portable-prover-rating.patch
python3 -m pip install .
agda-prover-rating demo demo-rating
```

If the checkout has changed, inspect any patch conflicts before applying. The
patch adds the agda-prover-rating command, its implementation and tests, the
protocol document, and a live CI check. It does not change proof search.

See prover-rating.md for the model, derivation, assumptions, input format,
AgdaProver configuration, and commands for running and comparing contestants.

## Evidence

The synthetic example uses true ratings of 1800, 1500, and 1200 and estimates
approximately 1797, 1500, and 1203. It is explicitly marked as simulation.

The real smoke test uses 16 self-contained tasks, Agda 2.8.0, and 10 seconds
per task, including independent checking. AgdaProver solved 11; the four-term
lambda baseline solved 4. The baseline has no sole-solver wins. Consequently,
the finite rating gap is prior-dependent and the report withholds intervals.
Do not present the smoke rating as an established rating of AgdaProver.

A mature scale needs a larger, held-out, reviewed task bank and a diverse
reference panel under controlled resources. This implementation supplies the
measurement machinery; it cannot create library- and distribution-free
mathematical strength from a small development sample.

validation/ contains the test logs and validation summary. examples/ contains
original result manifests, a checked task bank, accepted proofs, worker logs,
and Markdown/JSON reports. Original local command paths in recorded results
describe the execution environment; replace them using the protocol examples
when running on your own machine.

Code is supplied under the repository's GPL-3.0-or-later license.
