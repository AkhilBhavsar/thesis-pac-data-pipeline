output "monthly_budget_summary" {
  description = "Summary of the existing monthly account budget."

  value = {
    name            = data.aws_budgets_budget.monthly_cost.name
    budget_type     = data.aws_budgets_budget.monthly_cost.budget_type
    limit_amount    = tonumber(one(data.aws_budgets_budget.monthly_cost.budget_limit).amount)
    limit_unit      = one(data.aws_budgets_budget.monthly_cost.budget_limit).unit
    budget_exceeded = data.aws_budgets_budget.monthly_cost.budget_exceeded
  }
}

output "zero_spend_budget_summary" {
  description = "Summary of the existing zero-spend account budget."

  value = {
    name            = data.aws_budgets_budget.zero_spend.name
    budget_type     = data.aws_budgets_budget.zero_spend.budget_type
    limit_amount    = tonumber(one(data.aws_budgets_budget.zero_spend.budget_limit).amount)
    limit_unit      = one(data.aws_budgets_budget.zero_spend.budget_limit).unit
    budget_exceeded = data.aws_budgets_budget.zero_spend.budget_exceeded
  }
}
