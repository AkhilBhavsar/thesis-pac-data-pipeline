variable "aws_account_id" {
  description = "AWS account containing the existing account-level budgets."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "monthly_budget_name" {
  description = "Name of the existing monthly account cost budget."
  type        = string
  default     = "My Monthly Cost Budget"
}

variable "monthly_budget_limit_usd" {
  description = "Expected limit of the existing monthly account budget."
  type        = number
  default     = 2
}

variable "zero_spend_budget_name" {
  description = "Name of the existing zero-spend account budget."
  type        = string
  default     = "My Zero-Spend Budget"
}

variable "zero_spend_budget_limit_usd" {
  description = "Expected limit of the existing zero-spend budget."
  type        = number
  default     = 0.01
}
