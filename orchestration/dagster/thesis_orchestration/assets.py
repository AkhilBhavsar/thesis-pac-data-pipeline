import os

from dagster_dbt import (
    DbtCliResource,
    dbt_assets,
)

from thesis_orchestration.bronze_runtime import (
    BronzeGateResource,
    run_bronze_guarded_dbt,
)
from thesis_orchestration.paths import (
    DBT_EXECUTABLE,
    DBT_PROFILE_NAME,
    DBT_PROFILES_DIR,
    DBT_PROJECT_DIR,
    DBT_TARGET_NAME,
    MANIFEST_PATH,
)


DBT_ASSET_SELECTION = "tag:silver tag:gold"


dbt_resource = DbtCliResource(
    project_dir=str(DBT_PROJECT_DIR),
    profiles_dir=str(DBT_PROFILES_DIR),
    profile=DBT_PROFILE_NAME,
    target=DBT_TARGET_NAME,
    dbt_executable=DBT_EXECUTABLE,
    global_config_flags=[
        "--no-use-colors",
        "--no-version-check",
    ],
)


bronze_gate_resource = (
    BronzeGateResource(
        region_name=os.getenv(
            "THESIS_AWS_REGION",
            "eu-west-1",
        ),
        expected_bucket=os.getenv(
            "THESIS_BRONZE_BUCKET",
            (
                "thesis-pac-dev-data-lake-"
                "522814714524-eu-west-1"
            ),
        ),
        expected_prefix=os.getenv(
            "THESIS_BRONZE_PREFIX",
            "bronze/",
        ),
    )
)


@dbt_assets(
    manifest=MANIFEST_PATH,
    select=DBT_ASSET_SELECTION,
    name="thesis_dbt_assets",
)
def thesis_dbt_assets(
    context,
    dbt: DbtCliResource,
    bronze_gate: BronzeGateResource,
):
    """Execute dbt only after Bronze passes."""

    yield from run_bronze_guarded_dbt(
        context=context,
        dbt=dbt,
        bronze_gate=bronze_gate,
        manifest_path=MANIFEST_PATH,
    )
