output "role_names" {
  description = "Runtime IAM role names by AWS service."

  value = {
    glue           = aws_iam_role.glue_runtime.name
    lambda         = aws_iam_role.lambda_runtime.name
    c2_quarantine  = aws_iam_role.c2_quarantine_runtime.name
    step_functions = aws_iam_role.step_functions_runtime.name
  }
}

output "role_arns" {
  description = "Runtime IAM role ARNs by AWS service."

  value = {
    glue           = aws_iam_role.glue_runtime.arn
    lambda         = aws_iam_role.lambda_runtime.arn
    c2_quarantine  = aws_iam_role.c2_quarantine_runtime.arn
    step_functions = aws_iam_role.step_functions_runtime.arn
  }
}

output "policy_arns" {
  description = "Customer-managed runtime IAM policy ARNs."

  value = {
    glue           = aws_iam_policy.glue_runtime.arn
    lambda         = aws_iam_policy.lambda_runtime.arn
    c2_quarantine  = aws_iam_policy.c2_quarantine_runtime.arn
    step_functions = aws_iam_policy.step_functions_runtime.arn
  }
}
