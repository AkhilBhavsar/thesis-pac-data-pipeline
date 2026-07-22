provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project         = var.project_name
        Environment     = var.environment
        ManagedBy       = "Terraform"
        ThesisComponent = "InfrastructureBootstrap"
      },
      var.additional_tags
    )
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}
