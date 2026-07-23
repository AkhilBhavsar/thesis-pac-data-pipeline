output "project_budget_summary" {
  description = "Project-specific AWS Budget configuration."

  value = {
    name              = module.project_budget.name
    arn               = module.project_budget.arn
    monthly_limit_usd = module.project_budget.monthly_limit_usd
    cost_scope        = module.project_budget.cost_scope
  }
}
