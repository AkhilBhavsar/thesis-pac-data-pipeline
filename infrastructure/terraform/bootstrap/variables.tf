variable "aws_region" {
  description = "AWS region used for the Terraform backend resources."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region name."
  }
}

variable "project_name" {
  description = "Short lowercase project identifier used in resource names."
  type        = string
  default     = "thesis-pac"

  validation {
    condition = (
      length(var.project_name) >= 3 &&
      length(var.project_name) <= 30 &&
      can(regex("^[a-z0-9-]+$", var.project_name))
    )

    error_message = "project_name must contain 3-30 lowercase letters, numbers or hyphens."
  }
}

variable "environment" {
  description = "Environment represented by this Terraform configuration."
  type        = string
  default     = "bootstrap"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.environment))
    error_message = "environment must use lowercase letters, numbers or hyphens."
  }
}

variable "noncurrent_version_retention_days" {
  description = "Days to retain noncurrent Terraform state object versions."
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_version_retention_days >= 30
    error_message = "Terraform state versions must be retained for at least 30 days."
  }
}

variable "additional_tags" {
  description = "Additional tags applied to bootstrap resources."
  type        = map(string)
  default     = {}
}
