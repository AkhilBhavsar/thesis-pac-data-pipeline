variable "project_name" {
  description = "Project identifier used in the dbt Athena workgroup name."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes that one dbt Athena query may scan."
  type        = number
  default     = 1073741824

  validation {
    condition     = var.bytes_scanned_cutoff_per_query >= 10485760
    error_message = "Athena requires the per-query cutoff to be at least 10 MiB."
  }
}
