data "aws_budgets_budget" "monthly_cost" {
  account_id = var.aws_account_id
  name       = var.monthly_budget_name
}

data "aws_budgets_budget" "zero_spend" {
  account_id = var.aws_account_id
  name       = var.zero_spend_budget_name
}

check "monthly_budget_configuration" {
  assert {
    condition = (
      data.aws_budgets_budget.monthly_cost.budget_type == "COST" &&
      one(data.aws_budgets_budget.monthly_cost.budget_limit).unit == "USD" &&
      tonumber(one(data.aws_budgets_budget.monthly_cost.budget_limit).amount) == var.monthly_budget_limit_usd
    )

    error_message = "The existing monthly budget must be a USD 2 COST budget."
  }
}

check "zero_spend_budget_configuration" {
  assert {
    condition = (
      data.aws_budgets_budget.zero_spend.budget_type == "COST" &&
      one(data.aws_budgets_budget.zero_spend.budget_limit).unit == "USD" &&
      tonumber(one(data.aws_budgets_budget.zero_spend.budget_limit).amount) == var.zero_spend_budget_limit_usd
    )

    error_message = "The existing zero-spend budget must be a USD 0.01 COST budget."
  }
}
