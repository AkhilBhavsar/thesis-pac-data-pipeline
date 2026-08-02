from dagster_dbt import (
    DbtCliResource,
    dbt_assets,
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


@dbt_assets(
    manifest=MANIFEST_PATH,
    select=DBT_ASSET_SELECTION,
    name="thesis_dbt_assets",
)
def thesis_dbt_assets(
    context,
    dbt: DbtCliResource,
):
    """Execute only the dbt assets selected by Dagster."""

    yield from dbt.cli(
        ["build"],
        context=context,
    ).stream()
