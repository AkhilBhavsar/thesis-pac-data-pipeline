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
- [ ] Silver layer implemented
- [ ] Gold layer implemented
- [ ] Local baseline validated
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

The `main` branch represents the latest validated project state.

Development will be completed through controlled feature branches and pull requests.
