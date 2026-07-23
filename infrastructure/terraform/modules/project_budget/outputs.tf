output "name" {
  description = "Name of the project-specific AWS Budget."
  value       = aws_budgets_budget.this.name
}

output "arn" {
  description = "ARN of the project-specific AWS Budget."
  value       = aws_budgets_budget.this.arn
}

output "monthly_limit_usd" {
  description = "Configured monthly project budget limit."
  value       = tonumber(aws_budgets_budget.this.limit_amount)
}

output "cost_scope" {
  description = "Cost-allocation tags monitored by this budget."

  value = {
    Project     = var.project_name
    Environment = var.environment
  }
}
