output "data_lake_bucket_name" {
  description = "Name of the primary S3 data-lake bucket."
  value       = aws_s3_bucket.data_lake.id
}

output "data_lake_bucket_arn" {
  description = "ARN of the primary S3 data-lake bucket."
  value       = aws_s3_bucket.data_lake.arn
}

output "athena_results_bucket_name" {
  description = "Name of the Athena query-results bucket."
  value       = aws_s3_bucket.athena_results.id
}

output "athena_results_bucket_arn" {
  description = "ARN of the Athena query-results bucket."
  value       = aws_s3_bucket.athena_results.arn
}

output "athena_results_location" {
  description = "S3 URI used for Athena query results."
  value       = "s3://${aws_s3_bucket.athena_results.id}/results/"
}

output "data_prefixes" {
  description = "Governed data-lake prefixes."
  value       = sort(tolist(local.data_prefixes))
}
