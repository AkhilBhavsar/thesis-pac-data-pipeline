# Thesis Repository Conventions

This document defines the canonical naming and repository-hygiene rules for the thesis implementation and experiments.

## Experimental conditions

- `C0` — standard CI/CD baseline
- `C1` — CI/CD with Policy-as-Code gates
- `C2` — CI/CD with Policy-as-Code gates and bounded self-healing

## Canonical scenario IDs

- `schema_break`
- `pii_exposure`
- `freshness_breach`
- `quality_regression`
- `policy_false_positive`

Scenario IDs must not be replaced with synonyms in workflows, JSON, CSV, evidence, or experiment results.

## Branch naming

Use lowercase kebab-case.

Canonical C2 phase branch:

`feature/c2-bounded-self-healing`

Examples of valid focused branches:

- `feature/c2-remediation-planner`
- `feature/c2-remediation-executor`
- `feature/c2-quarantine-runtime`
- `feature/c2-aws-orchestration`

Do not use ambiguous names such as `test`, `final`, `latest`, `changes`, or `fix2`.

## Commit naming

Use:

`<type>(<scope>): <specific action>`

Examples:

- `feat(c2): add bounded remediation contracts`
- `feat(c2): implement remediation planner`
- `feat(quarantine): record bounded remediation events`
- `feat(ci): integrate C2 bounded self-healing workflow`
- `feat(terraform): provision C2 remediation runtime`
- `test(c2): validate remediation attempt bounds`
- `fix(c2): enforce fail-closed remediation fallback`

## GitHub workflow filenames

Workflow filenames must identify the condition and capability.

Examples:

- `c0-baseline.yml`
- `c1-pre-gate.yml`
- `c2-bounded-self-healing.yml`

Do not use generic filenames such as `test.yml`, `workflow.yml`, or `pipeline.yml`.

## GitHub workflow display names

Use a stable capability name, for example:

`name: C2 Bounded Self-Healing`

## GitHub Actions run names

Every scenario-capable workflow must define a dynamic `run-name:`.

Canonical visible structure:

`CONDITION | SCENARIO | PURPOSE | run #NUMBER.ATTEMPT`

Example:

`C2 | freshness_breach | authoritative-recovery | run #52.1`

The GitHub Actions page must make different scenarios distinguishable without opening the run.

## GitHub job names

Displayed job names must describe the responsibility.

Examples:

- `C2 | Policy Evaluation`
- `C2 | Bounded Remediation | freshness_breach`
- `C2 | Recovery Verification | quality_regression`

Do not use only `build`, `test`, `run`, or `job1` as displayed experiment job names.

## Run-purpose identifiers

Use lowercase kebab-case.

Canonical examples:

- `contract-validation`
- `planner-validation`
- `executor-validation`
- `containment-validation`
- `authoritative-recovery`
- `recovery-verification`
- `evidence-closure`
- `manual-review-validation`

## Artifact naming

Canonical template:

`c2-<scenario>-<purpose>-run-<run_id>-attempt-<attempt>`

Example:

`c2-freshness_breach-authoritative-recovery-run-32501234567-attempt-1`

Artifact names such as `artifact`, `results`, `output`, or `evidence` are not acceptable for authoritative experiments.

## External evidence directory naming

Canonical structure:

`c<condition>-<checkpoint>-<scenario-or-scope>-<purpose>-<UTC>`

Examples:

- `c2-01-foundation-bounded-remediation-contracts-20260820T090000Z`
- `c2-02-freshness_breach-remediation-planner-20260820T100000Z`
- `c2-09-quality_regression-authoritative-recovery-20260821T130000Z`
- `c2-10-consolidated-evidence-closure-20260822T180000Z`

## Evidence filenames

Prefer stable semantic filenames:

- `checkpoint.json`
- `run-context.json`
- `policy-decision-pre.json`
- `policy-decision-post.json`
- `remediation-plan.json`
- `remediation-result.json`
- `remediation-verification.json`
- `quarantine-event.json`
- `recovery-metrics.json`
- `run-final.json`
- `artifact-metadata.json`
- `commit.txt`
- `repository-status.txt`
- `SHA256SUMS`

Do not use ambiguous names such as `result1.json`, `temp.json`, or `final2.json`.

## Canonical C2 remediation actions

- `retry`
- `rollback`
- `quarantine`
- `redact_republish`
- `stop_promotion`
- `manual_review`

## Canonical terminal states

- `RECOVERED`
- `QUARANTINED`
- `MANUAL_REVIEW`
- `FAILED_SAFE`

## Canonical execution statuses

- `NOT_RUN`
- `SUCCEEDED`
- `FAILED`
- `TIMED_OUT`

## C2 checkpoint identifiers

- `C2_0_REPOSITORY_CONVENTIONS_BASELINE`
- `C2_1_BOUNDED_SELF_HEALING_CONTRACT_FOUNDATION`
- `C2_2_REMEDIATION_PLANNER`
- `C2_3_REMEDIATION_EXECUTOR`
- `C2_4_QUARANTINE_RUNTIME`
- `C2_5_RECOVERY_VERIFICATION`
- `C2_6_AWS_ORCHESTRATION`
- `C2_7_GITHUB_ACTIONS_INTEGRATION`
- `C2_8_LOCAL_VALIDATION`
- `C2_9_AUTHORITATIVE_EXPERIMENTS`
- `C2_10_CONSOLIDATED_EVIDENCE_CLOSURE`

## Authoritative GitHub run identity

Every authoritative experiment must preserve:

- condition
- scenario ID
- run purpose
- GitHub run ID
- run attempt
- job ID
- branch
- commit SHA
- workflow filename
- workflow display name
- artifact ID
- artifact name
- artifact SHA-256
- policy bundle SHA-256
- UTC timestamp

## Protected historical conditions

Formally closed C0 and C1 experimental evidence must not be rewritten merely to improve naming.

Historical naming imperfections remain part of the reproducible evidence trail.

## Repository hygiene

Do not commit transient runtime material such as:

- `.terraform/`
- `__pycache__/`
- `*.pyc`
- `.venv/`
- temporary virtual environments
- `transformations/dbt/target/`
- downloaded GitHub artifacts
- temporary evidence bundles
- scratch scripts
- macOS metadata files

## Acceptance criteria for future checkpoints

Every formal implementation checkpoint must verify:

- correct branch
- expected parent commit
- clean starting repository
- exact modified-file scope
- `git diff --check`
- exact staged-file scope
- exact committed-file scope
- remote parity
- clean final repository
- previous-condition protection where applicable

Every GitHub workflow checkpoint must additionally verify:

- descriptive workflow filename
- stable workflow name
- dynamic `run-name:`
- descriptive job name
- scenario-specific artifact name
- scenario-specific evidence identity

Naming and repository hygiene are formal acceptance criteria, not cosmetic cleanup.
