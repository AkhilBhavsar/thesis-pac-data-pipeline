# Policy-as-Code Data Pipeline with Bounded Self-Healing

## MSc Research Project

**Project title:**

Design and Evaluation of Policy-as-Code Gates with Bounded Self-Healing for Cloud-Native Data Pipeline CI/CD

## Research Aim

This project designs and evaluates a cloud-native e-commerce analytics data pipeline that combines:

- Policy-as-Code gates
- data contracts
- metadata governance
- runtime validation
- bounded self-healing
- controlled experimental evaluation

## Data Pipeline

Olist Source Data  
↓  
Bronze Layer  
↓  
Silver Layer  
↓  
Gold Internal / Gold Public  
↓  
Runtime Validation  
↓  
Trusted Publication or Quarantine

## Experimental Conditions

- **C0:** Baseline CI/CD
- **C1:** CI/CD with Policy-as-Code gates
- **C2:** CI/CD with Policy-as-Code and bounded self-healing

## Planned Scenarios

1. Breaking schema change
2. PII exposure in public output
3. Freshness breach
4. Silent data-quality regression
5. Policy false positive

## Current Status

- [x] Project structure created
- [x] Olist source data prepared
- [x] Governance metadata generated
- [x] Dataset contracts generated
- [x] Freshness-control data generated
- [x] Source-data profiling completed
- [x] Silver layer implemented
- [x] Silver layer validated
- [x] Gold layer implemented
- [x] Gold public-safe layer implemented
- [x] Gold data-quality and reconciliation validation completed
- [x] Gold contracts implemented and automatically validated
- [x] Gold deterministic-output verification completed
- [x] Local baseline C0 implemented and validated
- [ ] AWS cloud foundation provisioned
- [ ] Cloud baseline C0 implemented
- [ ] Policy-as-Code condition C1 implemented
- [ ] Bounded self-healing condition C2 implemented
- [ ] Experiments completed
- [ ] Results analysed

## Planned Technology Stack

- Python
- Pandas
- dbt Core
- Dagster
- Open Policy Agent
- Conftest
- GitHub Actions
- Terraform
- Amazon S3
- AWS Glue Data Catalog
- Amazon Athena
- Amazon CloudWatch
- AWS Lambda
- AWS Step Functions

## Repository Structure

- `data/` — data layers and profiling outputs
- `experiments/` — fault-injection and experiment results
- `governance/` — metadata, contracts and policies
- `infra/` — Infrastructure-as-Code
- `logs/` — runtime logs
- `scripts/` — data preparation and validation scripts
- `.github/` — GitHub Actions workflows

## Project Governance

## Local C0 Baseline

The local C0 reference pipeline executes the complete Silver-to-Gold
workflow without Policy-as-Code gates, bounded self-healing, or automatic
remediation.

Latest validated execution:

- Run ID: `local-c0-20260717T225142Z`
- Pipeline stages executed: 5
- Pipeline stages passed: 5
- Total runtime: 40.2440 seconds
- Silver validation: 53 checks passed
- Gold data-quality validation: 110 checks passed
- Gold contract validation: 211 checks passed
- C0 evidence validation: 31 checks passed
- Failed checks: 0
- Policy-as-Code enabled: false
- Bounded self-healing enabled: false
- Automatic remediation enabled: false

The recorded runtime represents one execution on the local development
machine. Repeated and cloud executions will be collected separately for
the controlled experimental comparison.



The `main` branch represents the latest validated project state.

Development will be completed through controlled feature branches and pull requests.
