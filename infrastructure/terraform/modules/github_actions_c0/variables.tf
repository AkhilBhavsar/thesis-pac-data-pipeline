variable "project_name" {
  description = "Project identifier used in IAM resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "aws_region" {
  description = "AWS region containing the governed pipeline."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account containing the governed pipeline."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to assume the C0 role."
  type        = string

  validation {
    condition = can(
      regex(
        "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
        var.github_repository
      )
    )

    error_message = "github_repository must use owner/repository format."
  }
}

variable "github_branch" {
  description = "Exact GitHub branch allowed to assume the C0 role."
  type        = string

  validation {
    condition     = length(trimspace(var.github_branch)) > 0
    error_message = "github_branch must not be empty."
  }
}

variable "github_owner_id" {
  description = "Immutable numeric GitHub owner ID."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must contain only digits."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain only digits."
  }
}

variable "data_lake_bucket_arn" {
  description = "ARN of the governed data-lake bucket."
  type        = string
}

variable "athena_results_bucket_arn" {
  description = "ARN of the Athena query-results bucket."
  type        = string
}

variable "dbt_athena_workgroup_arn" {
  description = "ARN of the dedicated dbt Athena workgroup."
  type        = string
}

variable "bronze_database_name" {
  description = "Canonical Bronze Glue database read by C0."
  type        = string
}

variable "shadow_database_prefix" {
  description = "Required prefix for isolated C0 Glue databases."
  type        = string
  default     = "thesis_pac_c0_"

  validation {
    condition = can(
      regex(
        "^[a-z0-9_]+_$",
        var.shadow_database_prefix
      )
    )

    error_message = "shadow_database_prefix must be lowercase and end with an underscore."
  }
}
