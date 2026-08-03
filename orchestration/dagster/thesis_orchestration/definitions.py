from __future__ import annotations

import dagster as dg
from dagster_dbt import (
    build_dbt_asset_selection,
)

from thesis_orchestration.assets import (
    bronze_gate_resource,
    dbt_resource,
    thesis_dbt_assets,
)


silver_selection = (
    build_dbt_asset_selection(
        [thesis_dbt_assets],
        dbt_select="tag:silver",
    )
)

gold_selection = (
    build_dbt_asset_selection(
        [thesis_dbt_assets],
        dbt_select="tag:gold",
    )
)

complete_pipeline_selection = (
    silver_selection
    | gold_selection
)


silver_dbt_job = dg.define_asset_job(
    name="silver_dbt_job",
    selection=silver_selection,
    description=(
        "Validate Bronze, then build and "
        "validate the ten governed Silver "
        "dbt assets."
    ),
)

gold_dbt_job = dg.define_asset_job(
    name="gold_dbt_job",
    selection=gold_selection,
    description=(
        "Validate Bronze, then build and "
        "validate the five governed Gold "
        "dbt assets."
    ),
)

bronze_silver_gold_job = (
    dg.define_asset_job(
        name="bronze_silver_gold_job",
        selection=(
            complete_pipeline_selection
        ),
        description=(
            "Require the governed Bronze "
            "availability gate before the "
            "Silver and Gold dbt build."
        ),
    )
)


defs = dg.Definitions(
    assets=[
        thesis_dbt_assets,
    ],
    jobs=[
        silver_dbt_job,
        gold_dbt_job,
        bronze_silver_gold_job,
    ],
    resources={
        "dbt": dbt_resource,
        "bronze_gate": (
            bronze_gate_resource
        ),
    },
)
