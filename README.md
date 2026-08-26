# Policy-as-Code Data Pipeline with Bounded Self-Healing

MSc research artefact for the design and controlled evaluation of Policy-as-Code governance and bounded self-healing in a cloud-native e-commerce analytics pipeline.

## Project status

The practical implementation and authoritative experiment are complete.

- **45 of 45** authoritative observations accepted
- **3 conditions × 5 scenarios × 3 replications**
- **0** accepted technical failures
- **0** canonical-data mutations
- Complete timing coverage and SHA-256-locked evidence
- Final metrics workbook, thesis figures and H1/H2 evaluation generated

One external OPA-download failure was preserved as a technical exclusion and replaced transparently. It is not counted among the 45 accepted observations.

## Experimental conditions

| Condition | Treatment | Frozen commit | Permanent tag |
|---|---|---|---|
| C0 | Standard CI/CD comparator | `1b0aaf720dac79c0f48056a06695b74857fd66bc` | `thesis-c0-final` |
| C1 | CI/CD with Policy-as-Code gates | `0bd2140e509be1697dffa7b08a9ccbfc74d72953` | `thesis-c1-final` |
| C2 | CI/CD with Policy-as-Code and bounded self-healing | `f3a4d7fbc684b40422fb498dda782be61355f656` | `thesis-c2-final` |

The three condition branches are intentionally separate experimental treatments and should not be merged into one implementation.

## Evaluated scenarios

1. Breaking schema change
2. PII exposure in public output
3. Freshness breach
4. Silent data-quality regression
5. Policy false positive using a deliberately safe additive change

## Headline results

| Metric | C0 | C1 | C2 |
|---|---:|---:|---:|
| Unsafe outcomes prevented | 6/12 (50%) | 12/12 (100%) | 12/12 (100%) |
| Runtime-incident / unsafe-output-escape proxy | 6/12 (50%) | 0/12 (0%) | 0/12 (0%) |
| Safe-change stress false-positive rate | 0/3 (0%) | 3/3 (100%) | 3/3 (100%) |
| Manual-intervention rate | 12/15 (80%) | 15/15 (100%) | 12/15 (80%) |
| Mean active treatment duration | 304.2 s | 168.9 s | 291.7 s |

C2 produced three verified automated PII recoveries with a mean verified recovery time of **841.665 seconds (14.03 minutes)**. Its remaining unsafe outcomes ended in controlled quarantine or manual-review handoffs.

These are controlled descriptive results. Runtime incidents are isolated experimental proxies, and the deliberate safe-change scenario is not an estimate of production false-positive prevalence.

## Pipeline architecture

```text
Olist sources
    ↓
Amazon S3 Bronze → AWS Glue Data Catalog
    ↓
Dagster orchestration + dbt transformations
    ↓
Silver → Gold internal / Gold public
    ↓
OPA/Conftest policy decisions
    ↓
Trusted publication, verified recovery, quarantine, or manual review
```

## Technology

- Python, dbt Core and Dagster
- Open Policy Agent and Conftest
- GitHub Actions with AWS OIDC
- Terraform
- Amazon S3, Glue Data Catalog and Athena
- AWS Lambda, Step Functions and CloudWatch

## Repository navigation

- `.github/workflows/` — manual-only C0, C1 and C2 experiment workflows
- `orchestration/dagster/` — orchestration assets and runtime checks
- `transformations/dbt/` — Silver and Gold transformations and tests
- `policies/` — policy catalogue, Rego rules, fixtures and contracts
- `scripts/` — scenario injection, policy evaluation and remediation logic
- `runtime/` — bounded C2 runtime components
- `infrastructure/terraform/` — AWS infrastructure and cost controls
- `tests/` — policy and remediation regression tests
- `governance/` — data contracts and metadata

## Reproducibility and evidence

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for the frozen execution boundary, evidence rules, metric definitions and verification process. See [docs/RESULTS_SUMMARY.md](docs/RESULTS_SUMMARY.md) for the thesis-aligned findings and limitations.

The workflows are intentionally `workflow_dispatch` only. Do not rerun authoritative cells after the dataset lock.
