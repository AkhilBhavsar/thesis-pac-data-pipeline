output "workgroup_name" {
  description = "Name of the governed Athena workgroup."
  value       = aws_athena_workgroup.this.name
}

output "workgroup_arn" {
  description = "ARN of the governed Athena workgroup."
  value       = aws_athena_workgroup.this.arn
}

output "results_location" {
  description = "Enforced Athena query-results location."
  value       = var.results_location
}

output "bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes that one Athena query may scan."
  value       = var.bytes_scanned_cutoff_per_query
}
