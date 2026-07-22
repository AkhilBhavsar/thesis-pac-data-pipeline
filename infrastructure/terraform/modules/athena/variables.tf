variable "project_name" {
  description = "Project identifier used in the Athena workgroup name."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "results_location" {
  description = "S3 URI used for Athena query results."
  type        = string

  validation {
    condition     = can(regex("^s3://.+/$", var.results_location))
    error_message = "results_location must be an S3 URI ending with a slash."
  }
}

variable "expected_bucket_owner" {
  description = "AWS account expected to own the Athena results bucket."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_bucket_owner))
    error_message = "expected_bucket_owner must contain exactly 12 digits."
  }
}

variable "bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes that one Athena query may scan."
  type        = number
  default     = 1073741824

  validation {
    condition     = var.bytes_scanned_cutoff_per_query >= 10485760
    error_message = "Athena requires the per-query cutoff to be at least 10 MiB."
  }
}
