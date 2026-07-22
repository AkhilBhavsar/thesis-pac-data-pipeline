variable "project_name" {
  description = "Project identifier used in Glue database names."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account that owns the Glue Data Catalog."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "data_lake_bucket_name" {
  description = "S3 bucket containing the governed data zones."
  type        = string
}
