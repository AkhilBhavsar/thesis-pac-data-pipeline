# Authoritative Results Summary

## Evidence completeness

The final evaluation contains 45 accepted authoritative observations with complete timing and locked evidence. The design is balanced at 15 observations per condition, nine per scenario and 15 per replication. No accepted observation produced a canonical mutation.

## Comparative results

| Condition | Prevention | Runtime incident / escape proxy | Safe-change false positive | Manual intervention | Mean active treatment |
|---|---:|---:|---:|---:|---:|
| C0 — Standard CI/CD | 50% | 50% | 0% | 80% | 304.2 s |
| C1 — Policy-as-Code | 100% | 0% | 100% | 100% | 168.9 s |
| C2 — Policy-as-Code + bounded self-healing | 100% | 0% | 100% | 80% | 291.7 s |

C0 controlled all schema and PII observations through standard tests but missed all six post-execution freshness and quality faults. C1 and C2 controlled all 12 unsafe observations in each condition.

## C2 recovery and controlled handoff

Across 12 unsafe C2 observations:

- 3 verified automated recoveries (25%)
- 6 controlled quarantine handoffs (50%)
- 3 controlled manual-review handoffs (25%)

All three eligible PII observations were recovered and verified. Mean verified MTTR was 841.665 seconds (14.03 minutes; sample SD 330.050 seconds). Quarantine and manual-review outcomes are censored because trusted output was not automatically restored.

## Policy quality and overhead

The safe additive-change stress scenario was denied in all three C1 and C2 replications. This demonstrates a policy-maintenance limitation and is not an estimate of normal production prevalence.

C1 policy evaluation averaged 17.115 ms. C2 active treatment averaged 291.7 seconds, 122.7 seconds (72.7%) more than C1. The added time came primarily from the bounded-remediation wrapper rather than policy evaluation.

## Hypotheses

- **H1: supported descriptively.** Policy-gated conditions reduced the isolated runtime-incident/unsafe-output-escape proxy from 50% under C0 to 0% under C1 and C2.
- **H2: partially supported with a scope limitation.** C2 achieved verified automated recovery in all three eligible PII replications. C1 generated no finite recovery time, so a numerical C1-to-C2 MTTR reduction cannot be estimated.

## Interpretation limits

- Three replications per condition-scenario cell provide limited inferential power.
- Results support controlled descriptive comparison rather than universal causal claims.
- Runtime incidents and unsafe-output escapes are isolated experimental proxies.
- The false-positive result is specific to a deliberately injected safe-change stress scenario.
- Only terminal `RECOVERED` outcomes with verification `PASS` contribute to MTTR.
