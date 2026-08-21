output "aws_account_id" {
  description = "AWS account containing the development environment."
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region containing the development environment."
  value       = var.aws_region
}

output "data_lake_bucket_name" {
  description = "Primary data-lake bucket."
  value       = module.data_lake.data_lake_bucket_name
}

output "data_lake_bucket_arn" {
  description = "Primary data-lake bucket ARN."
  value       = module.data_lake.data_lake_bucket_arn
}

output "athena_results_bucket_name" {
  description = "Athena query-results bucket."
  value       = module.data_lake.athena_results_bucket_name
}

output "athena_results_location" {
  description = "Athena output S3 URI."
  value       = module.data_lake.athena_results_location
}

output "data_prefixes" {
  description = "Governed data-lake prefixes."
  value       = module.data_lake.data_prefixes
}

output "glue_database_names" {
  description = "Glue databases by governed data zone."
  value       = module.glue_catalog.database_names
}

output "athena_workgroup_name" {
  description = "Governed Athena workgroup."
  value       = module.athena.workgroup_name
}

output "athena_workgroup_arn" {
  description = "Governed Athena workgroup ARN."
  value       = module.athena.workgroup_arn
}

output "athena_bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes allowed per Athena query."
  value       = module.athena.bytes_scanned_cutoff_per_query
}

output "monthly_budget_summary" {
  description = "Existing monthly AWS budget summary."
  value       = module.cost_controls.monthly_budget_summary
}

output "zero_spend_budget_summary" {
  description = "Existing zero-spend AWS budget summary."
  value       = module.cost_controls.zero_spend_budget_summary
}

output "runtime_iam_role_names" {
  description = "Runtime IAM role names by AWS service."
  value       = module.runtime_iam.role_names
}

output "runtime_iam_role_arns" {
  description = "Runtime IAM role ARNs by AWS service."
  value       = module.runtime_iam.role_arns
}

output "runtime_iam_policy_arns" {
  description = "Runtime IAM policy ARNs by AWS service."
  value       = module.runtime_iam.policy_arns
}

output "dbt_athena_workgroup_name" {
  description = "Dedicated Athena workgroup for dbt transformations."
  value       = module.athena_dbt.workgroup_name
}

output "dbt_athena_workgroup_arn" {
  description = "ARN of the dedicated dbt Athena workgroup."
  value       = module.athena_dbt.workgroup_arn
}

output "dbt_athena_bytes_scanned_cutoff_per_query" {
  description = "Maximum bytes allowed per dbt Athena query."
  value       = module.athena_dbt.bytes_scanned_cutoff_per_query
}

output "dbt_glue_database_name" {
  description = "Glue database used for controlled dbt transformations."
  value       = module.glue_catalog.dbt_database_name
}

output "github_actions_c0_oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
  value       = module.github_actions_c0.oidc_provider_arn
}

output "github_actions_c0_role_name" {
  description = "Name of the isolated C0 GitHub Actions role."
  value       = module.github_actions_c0.role_name
}

output "github_actions_c0_role_arn" {
  description = "ARN of the isolated C0 GitHub Actions role."
  value       = module.github_actions_c0.role_arn
}

output "github_actions_c0_policy_arn" {
  description = "ARN of the isolated C0 GitHub Actions policy."
  value       = module.github_actions_c0.policy_arn
}

output "github_actions_c0_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the C0 role."
  value       = module.github_actions_c0.github_subject
}

output "github_actions_c1_role_name" {
  description = "Name of the isolated C1 GitHub Actions IAM role."
  value       = module.github_actions_c1.role_name
}

output "github_actions_c1_role_arn" {
  description = "ARN of the isolated C1 GitHub Actions IAM role."
  value       = module.github_actions_c1.role_arn
}

output "github_actions_c1_policy_arn" {
  description = "ARN of the isolated C1 GitHub Actions IAM policy."
  value       = module.github_actions_c1.policy_arn
}

output "github_actions_c1_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the C1 role."
  value       = module.github_actions_c1.github_subject
}

output "c2_quarantine_lambda_name" {
  description = "C2 bounded-remediation quarantine Lambda function name."
  value       = aws_lambda_function.c2_quarantine.function_name
}

output "c2_quarantine_lambda_arn" {
  description = "ARN of the C2 bounded-remediation quarantine Lambda function."
  value       = aws_lambda_function.c2_quarantine.arn
}

output "github_actions_c2_role_name" {
  description = "Name of the isolated C2 GitHub Actions IAM role."
  value       = module.github_actions_c2.role_name
}

output "github_actions_c2_role_arn" {
  description = "ARN of the isolated C2 GitHub Actions IAM role."
  value       = module.github_actions_c2.role_arn
}

output "github_actions_c2_policy_arn" {
  description = "ARN of the isolated C2 GitHub Actions IAM policy."
  value       = module.github_actions_c2.policy_arn
}

output "github_actions_c2_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the C2 role."
  value       = module.github_actions_c2.github_subject
}

output "c2_fallback_state_machine_name" {
  description = "Name of the C2 bounded fallback Step Functions state machine."
  value       = aws_sfn_state_machine.c2_fallback.name
}

output "c2_fallback_state_machine_arn" {
  description = "ARN of the C2 bounded fallback Step Functions state machine."
  value       = aws_sfn_state_machine.c2_fallback.arn
}

output "c2_observability_alarm_names" {
  description = "CloudWatch alarms covering initial C2 fallback reliability signals."

  value = [
    aws_cloudwatch_metric_alarm.c2_quarantine_errors.alarm_name,
    aws_cloudwatch_metric_alarm.c2_fallback_executions_failed.alarm_name,
    aws_cloudwatch_metric_alarm.c2_fallback_executions_timed_out.alarm_name
  ]
}
