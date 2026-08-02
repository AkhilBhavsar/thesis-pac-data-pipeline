# Thesis Dagster orchestration

This package exposes the existing governed dbt transformations as Dagster
software-defined assets.

## Current asset boundary

- Bronze: 10 dbt source dependencies
- Silver: 10 materialized dbt assets
- Gold Internal: 4 materialized dbt assets
- Gold Public: 1 materialized dbt asset
- Intermediate Gold: 2 ephemeral dbt models

## Jobs

- `silver_dbt_job`
- `gold_dbt_job`
- `bronze_silver_gold_job`

## Runtime configuration

- `THESIS_DBT_MANIFEST_PATH`
- `THESIS_DBT_PROFILES_DIR`
- `THESIS_DBT_EXECUTABLE`

This foundation checkpoint validates definitions and jobs only. It does not
execute dbt models, submit Athena queries or mutate AWS.
