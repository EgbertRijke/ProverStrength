# Portable Prover Rating

Track: `SIMULATION-v1`; budget: 10.0 seconds; anchor: simulated-reference = 1500.

A 400-point advantage represents 10:1 model odds of being the sole solver, conditional on exactly one of the two provers solving a matched task.

| Prover | Rating | Family bootstrap 95% interval | Balanced solved |
| --- | ---: | --- | ---: |
| simulated-strong | 1797 | 1730–1859 | 71.3% |
| simulated-reference | 1500 | fixed reference | 49.7% |
| simulated-weak | 1203 | 1131–1254 | 26.5% |

Domain solve rates (equal weight per family):

| Prover | dependent | equality | induction | logic |
| --- | ---: | ---: | ---: | ---: |
| simulated-strong | 74.0% | 68.0% | 67.3% | 76.0% |
| simulated-reference | 50.0% | 40.0% | 56.0% | 52.7% |
| simulated-weak | 26.7% | 22.7% | 28.7% | 28.0% |

Independent sampling units: 200 families. Bootstrap draws: 200. Maximum rating shift on doubling the prior SD: 1.5 points.

- SIMULATED outcomes: these are not measurements of real provers.

Intervals describe sampling variability of the regularized estimate on the declared family population. They are not guarantees about unseen domains. The anchor's zero-width interval is a convention, not perfect knowledge of its performance.

Suite fingerprint: `4af3854c74b78512195ac80dd25813b35bb42657e2fce845443df6e994b7d073`.
Results fingerprint: `5c85e70d96d55d1e0461acde8ea32e25b8546d92c90689aaff96393c932ed4c0`.
