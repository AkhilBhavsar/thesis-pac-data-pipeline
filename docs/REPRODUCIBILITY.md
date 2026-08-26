# Reproducibility and Evidence Protocol

## Frozen implementation boundary

| Condition | Branch | Commit |
|---|---|---|
| C0 | `feature/dagster-orchestration` | `1b0aaf720dac79c0f48056a06695b74857fd66bc` |
| C1 | `feature/policy-as-code-gates` | `0bd2140e509be1697dffa7b08a9ccbfc74d72953` |
| C2 | `feature/c2-bounded-self-healing` | `f3a4d7fbc684b40422fb498dda782be61355f656` |

The branches are separate research conditions. Reproducing an observation requires selecting the matching branch, workflow and scenario; substituting another branch changes the treatment.

## Experimental matrix

The locked matrix contains 45 accepted observations:

- 3 conditions: C0, C1 and C2
- 5 scenarios: schema break, PII exposure, freshness breach, quality regression and policy false positive
- 3 replications per condition-scenario cell

Runs were executed sequentially through manual GitHub Actions dispatches. Every observation was accepted only after identity, artifact integrity, semantic outcome and canonical-safety adjudication passed.

## Workflow conclusion semantics

A red GitHub conclusion is not automatically a technical failure:

- C0 schema and PII failures are valid observations when standard pipeline tests detect the injected fault.
- C1 failures are valid when the exact policy gate returns the expected controlled `DENY` and blocks promotion.
- C2 success represents completion of the bounded control wrapper; the semantic result may be verified recovery, quarantine or manual review.

The semantic adjudication artifact, rather than colour alone, determines validity.

## Evidence rules

- Exactly one workflow dispatch per accepted observation.
- Run branch, commit, run ID and attempt must match the frozen cell.
- Artifacts are downloaded and integrity-locked before acceptance.
- Canonical mutation must remain false.
- Technical failures are excluded transparently and preserved.
- No accepted observation is silently omitted.

Run `32895452190` was excluded because the external OPA distribution download failed during setup. A separately authorised replacement was executed and accepted.

## Metric definitions

- **Unsafe prevention:** an unsafe experimental outcome was blocked, safely recovered, quarantined or handed to manual review before trusted promotion.
- **Runtime incident / unsafe-output escape proxy:** an isolated injected unsafe outcome escaped the tested condition's control. This does not represent canonical corruption.
- **False positive:** the deliberately safe additive-change scenario was denied.
- **Verified recovery:** terminal state `RECOVERED` with verification `PASS`.
- **MTTR:** calculated only for verified recoveries; quarantine and manual-review outcomes are censored.
- **C2 active treatment duration:** matching C1 workflow duration plus C2 wrapper duration, excluding human/controller dispatch gaps.

## Locked analysis boundary

- Accepted observations: 45/45
- Accepted timing coverage: 45/45
- Accepted technical failures: 0
- Canonical mutations: 0
- Excluded technical attempts: 1, explicitly recorded

The final results release includes the workbook, thesis figures, enriched observation table, reference metrics and a `SHA256SUMS` file. Verify downloaded release assets using:

```bash
shasum -a 256 -c SHA256SUMS
```

## Safety

- Do not rerun the authoritative matrix after the dataset lock.
- Do not merge the three condition branches.
- Do not modify or overwrite locked evidence.
- Do not delete AWS experimental resources until their exact targets have been reviewed.
- Never commit AWS credentials, raw tokens or unredacted local logs.
