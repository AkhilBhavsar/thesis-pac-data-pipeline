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
