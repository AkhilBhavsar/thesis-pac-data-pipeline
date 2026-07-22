module "data_lake" {
  source = "../../modules/data_lake"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id

  data_noncurrent_version_retention_days = 90
  athena_results_retention_days          = 30
}
