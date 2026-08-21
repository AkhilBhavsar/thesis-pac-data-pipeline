output "role_name" {
  description = "Name of the isolated C1 GitHub Actions role."
  value       = aws_iam_role.c1.name
}

output "role_arn" {
  description = "ARN of the isolated C1 GitHub Actions role."
  value       = aws_iam_role.c1.arn
}

output "policy_arn" {
  description = "ARN of the isolated C1 GitHub Actions policy."
  value       = aws_iam_policy.c1.arn
}

output "github_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the C1 role."
  value       = local.github_subject
}
