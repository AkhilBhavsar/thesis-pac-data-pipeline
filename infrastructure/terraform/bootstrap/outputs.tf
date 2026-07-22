output "aws_account_id" {
  description = "AWS account containing the Terraform backend."
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region containing the Terraform backend."
  value       = var.aws_region
}

output "state_bucket_name" {
  description = "S3 bucket used to store remote Terraform state."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN of the Terraform state bucket."
  value       = aws_s3_bucket.terraform_state.arn
}

output "recommended_backend_configuration" {
  description = "Recommended backend settings for the development environment."

  value = {
    bucket       = aws_s3_bucket.terraform_state.id
    key          = "environments/dev/terraform.tfstate"
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}
