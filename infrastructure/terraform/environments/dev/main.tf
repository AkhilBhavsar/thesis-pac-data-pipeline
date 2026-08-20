module "data_lake" {
  source = "../../modules/data_lake"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  data_noncurrent_version_retention_days = 90
  athena_results_retention_days          = 30
}

module "glue_catalog" {
  source = "../../modules/glue_catalog"

  project_name          = var.project_name
  environment           = var.environment
  aws_account_id        = data.aws_caller_identity.current.account_id
  data_lake_bucket_name = module.data_lake.data_lake_bucket_name

  bronze_query_compatible_manifest = (
    local.bronze_query_compatible_manifest
  )

  bronze_supporting_manifest = (
    local.bronze_supporting_manifest
  )
}

module "athena" {
  source = "../../modules/athena"

  project_name          = var.project_name
  environment           = var.environment
  results_location      = module.data_lake.athena_results_location
  expected_bucket_owner = data.aws_caller_identity.current.account_id

  bytes_scanned_cutoff_per_query = 1073741824
}

module "athena_dbt" {
  source = "../../modules/athena_dbt"

  project_name = var.project_name
  environment  = var.environment

  bytes_scanned_cutoff_per_query = 1073741824
}

module "cost_controls" {
  source = "../../modules/cost_controls"

  aws_account_id = data.aws_caller_identity.current.account_id
}

module "runtime_iam" {
  source = "../../modules/runtime_iam"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  data_lake_bucket_arn      = module.data_lake.data_lake_bucket_arn
  athena_results_bucket_arn = module.data_lake.athena_results_bucket_arn
  athena_workgroup_arn      = module.athena.workgroup_arn
  glue_database_names       = module.glue_catalog.database_names
}

module "github_actions_c0" {
  source = "../../modules/github_actions_c0"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  github_repository    = "AkhilBhavsar/thesis-pac-data-pipeline"
  github_branch        = "feature/dagster-orchestration"
  github_owner_id      = "68535071"
  github_repository_id = "1302169914"

  data_lake_bucket_arn = (
    module.data_lake.data_lake_bucket_arn
  )

  athena_results_bucket_arn = (
    module.data_lake.athena_results_bucket_arn
  )

  dbt_athena_workgroup_arn = (
    module.athena_dbt.workgroup_arn
  )

  canonical_read_database_names = [
    module.glue_catalog.database_names["silver"],
    module.glue_catalog.database_names["gold_internal"],
    module.glue_catalog.database_names["gold_public"]
  ]

  bronze_database_name = (
    module.glue_catalog.database_names["bronze"]
  )
}

module "github_actions_c1" {
  source = "../../modules/github_actions_c1"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  github_repository    = "AkhilBhavsar/thesis-pac-data-pipeline"
  github_branch        = "feature/policy-as-code-gates"
  github_owner_id      = "68535071"
  github_repository_id = "1302169914"

  github_oidc_provider_arn = (
    module.github_actions_c0.oidc_provider_arn
  )

  data_lake_bucket_arn = (
    module.data_lake.data_lake_bucket_arn
  )

  athena_results_bucket_arn = (
    module.data_lake.athena_results_bucket_arn
  )

  dbt_athena_workgroup_arn = (
    module.athena_dbt.workgroup_arn
  )

  canonical_read_database_names = [
    module.glue_catalog.database_names["silver"],
    module.glue_catalog.database_names["gold_internal"],
    module.glue_catalog.database_names["gold_public"]
  ]

  bronze_database_name = (
    module.glue_catalog.database_names["bronze"]
  )

  shadow_database_prefix = "thesis_pac_c1_"
}

module "github_actions_c2" {
  source = "../../modules/github_actions_c2"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  github_repository    = "AkhilBhavsar/thesis-pac-data-pipeline"
  github_branch        = "feature/c2-bounded-self-healing"
  github_owner_id      = "68535071"
  github_repository_id = "1302169914"

  github_oidc_provider_arn = (
    module.github_actions_c0.oidc_provider_arn
  )

  data_lake_bucket_arn = (
    module.data_lake.data_lake_bucket_arn
  )

  athena_results_bucket_arn = (
    module.data_lake.athena_results_bucket_arn
  )

  dbt_athena_workgroup_arn = (
    module.athena_dbt.workgroup_arn
  )

  canonical_read_database_names = [
    module.glue_catalog.database_names["silver"],
    module.glue_catalog.database_names["gold_internal"],
    module.glue_catalog.database_names["gold_public"]
  ]

  bronze_database_name = (
    module.glue_catalog.database_names["bronze"]
  )

  shadow_database_prefix = "thesis_pac_c2_"

  c2_fallback_state_machine_arn = (
    aws_sfn_state_machine.c2_fallback.arn
  )
}
