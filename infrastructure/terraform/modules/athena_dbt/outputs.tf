output "workgroup_name" {
  description = "Name of the dedicated dbt Athena workgroup."
  value       = aws_athena_workgroup.this.name
}

output "workgroup_arn" {
  description = "ARN of the dedicated dbt Athena workgroup."
  value       = aws_athena_workgroup.this.arn
}

output "bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes that one dbt Athena query may scan."
  value       = var.bytes_scanned_cutoff_per_query
}
