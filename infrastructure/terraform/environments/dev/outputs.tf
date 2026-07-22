output "aws_account_id" {
  description = "AWS account containing the development environment."
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region containing the development environment."
  value       = var.aws_region
}

output "data_lake_bucket_name" {
  description = "Primary data-lake bucket."
  value       = module.data_lake.data_lake_bucket_name
}

output "data_lake_bucket_arn" {
  description = "Primary data-lake bucket ARN."
  value       = module.data_lake.data_lake_bucket_arn
}

output "athena_results_bucket_name" {
  description = "Athena query-results bucket."
  value       = module.data_lake.athena_results_bucket_name
}

output "athena_results_location" {
  description = "Athena output S3 URI."
  value       = module.data_lake.athena_results_location
}

output "data_prefixes" {
  description = "Governed data-lake prefixes."
  value       = module.data_lake.data_prefixes
}

output "glue_database_names" {
  description = "Glue databases by governed data zone."
  value       = module.glue_catalog.database_names
}

output "athena_workgroup_name" {
  description = "Governed Athena workgroup."
  value       = module.athena.workgroup_name
}

output "athena_workgroup_arn" {
  description = "Governed Athena workgroup ARN."
  value       = module.athena.workgroup_arn
}

output "athena_bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes allowed per Athena query."
  value       = module.athena.bytes_scanned_cutoff_per_query
}

output "monthly_budget_summary" {
  description = "Existing monthly AWS budget summary."
  value       = module.cost_controls.monthly_budget_summary
}

output "zero_spend_budget_summary" {
  description = "Existing zero-spend AWS budget summary."
  value       = module.cost_controls.zero_spend_budget_summary
}

output "runtime_iam_role_names" {
  description = "Runtime IAM role names by AWS service."
  value       = module.runtime_iam.role_names
}

output "runtime_iam_role_arns" {
  description = "Runtime IAM role ARNs by AWS service."
  value       = module.runtime_iam.role_arns
}

output "runtime_iam_policy_arns" {
  description = "Runtime IAM policy ARNs by AWS service."
  value       = module.runtime_iam.policy_arns
}
