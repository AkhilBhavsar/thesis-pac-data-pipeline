variable "project_name" {
  description = "Project identifier used in S3 bucket names."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "aws_region" {
  description = "AWS region containing the S3 buckets."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID used to create globally unique bucket names."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "data_noncurrent_version_retention_days" {
  description = "Retention period for previous data-lake object versions."
  type        = number
  default     = 90

  validation {
    condition     = var.data_noncurrent_version_retention_days >= 30
    error_message = "Previous data versions must be retained for at least 30 days."
  }
}

variable "athena_results_retention_days" {
  description = "Retention period for Athena query-result objects."
  type        = number
  default     = 30

  validation {
    condition     = var.athena_results_retention_days >= 7
    error_message = "Athena results must be retained for at least seven days."
  }
}
