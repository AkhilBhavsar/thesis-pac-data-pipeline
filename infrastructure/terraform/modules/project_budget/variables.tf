variable "aws_account_id" {
  description = "AWS account that owns the project budget."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "project_name" {
  description = "Value of the Project cost-allocation tag."
  type        = string
}

variable "environment" {
  description = "Value of the Environment cost-allocation tag."
  type        = string
}

variable "monthly_limit_usd" {
  description = "Maximum planned monthly project cost in USD."
  type        = number
  default     = 2

  validation {
    condition     = var.monthly_limit_usd > 0
    error_message = "monthly_limit_usd must be greater than zero."
  }
}

variable "alert_email" {
  description = "Email address receiving project budget notifications."
  type        = string
  sensitive   = true
}
