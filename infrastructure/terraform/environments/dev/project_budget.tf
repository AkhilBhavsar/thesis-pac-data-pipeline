variable "project_budget_alert_email" {
  description = "Email address receiving project-specific AWS Budget alerts."
  type        = string
  sensitive   = true
}

module "project_budget" {
  source = "../../modules/project_budget"

  aws_account_id    = data.aws_caller_identity.current.account_id
  project_name      = "thesis-pac"
  environment       = "dev"
  monthly_limit_usd = 2
  alert_email       = var.project_budget_alert_email
}
