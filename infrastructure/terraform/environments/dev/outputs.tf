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
