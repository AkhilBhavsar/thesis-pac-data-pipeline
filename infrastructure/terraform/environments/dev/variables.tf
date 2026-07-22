variable "aws_region" {
  description = "AWS region for the cloud-native data pipeline."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Short lowercase project identifier."
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
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "additional_tags" {
  description = "Additional tags for AWS resources."
  type        = map(string)

  default = {
    Application = "PolicyAsCodeDataPipeline"
    Purpose     = "MScThesisResearch"
    Owner       = "Researcher"
  }
}
