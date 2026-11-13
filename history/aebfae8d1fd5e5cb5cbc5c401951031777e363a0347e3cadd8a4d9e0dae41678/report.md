# Portable prover rating

Track: `agda-intensional-without-K-exact-split-v1`; budget: 10 seconds; anchor: lambda-baseline-v1 = 1500.

A 400-point advantage represents 10:1 model odds of being the sole solver, conditional on exactly one of the two provers solving a matched task.

| Prover | Rating | Family bootstrap 95% interval | Balanced solved |
| --- | ---: | --- | ---: |
| AgdaProver-nnue-deep | 2138 | unavailable | 68.8% |
| lambda-baseline-v1 | 1500 | fixed reference | 25.0% |

Domain solve rates (equal weight per family):

| Prover | dependent | equality | induction | logic |
| --- | ---: | ---: | ---: | ---: |
| AgdaProver-nnue-deep | 75.0% | 100.0% | 0.0% | 100.0% |
| lambda-baseline-v1 | 0.0% | 0.0% | 0.0% | 100.0% |

Independent sampling units: 16 families. Bootstrap draws: 200. Maximum rating shift on doubling the prior SD: 197.0 points.

- Small family sample: ratings are provisional; renamed tasks are not new families.
- Complete/quasi separation: finite ratings depend on the prior; intervals withheld.

Intervals describe sampling variability of the regularized estimate on the declared family population. They are not guarantees about unseen domains. The anchor's zero-width interval is a convention, not perfect knowledge of its performance.

Suite fingerprint: `babcb1ffeba51025e8351a275fe1b2a0cbf809c8af0f6938e097a7e901e40500`.
Results fingerprint: `fc69d5c4fc83f6b2344dc910ad86828d7bc8d4af7c95835076d74a5224bcaf00`.
