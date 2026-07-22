variable "project_name" {
  description = "Project identifier used in IAM resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "aws_region" {
  description = "AWS region containing the runtime resources."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account containing the runtime resources."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "data_lake_bucket_arn" {
  description = "ARN of the thesis data-lake bucket."
  type        = string
}

variable "athena_results_bucket_arn" {
  description = "ARN of the Athena query-results bucket."
  type        = string
}

variable "athena_workgroup_arn" {
  description = "ARN of the governed Athena workgroup."
  type        = string
}

variable "glue_database_names" {
  description = "Glue database names indexed by governed data zone."
  type        = map(string)
}
