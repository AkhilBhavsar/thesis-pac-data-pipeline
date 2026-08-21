output "role_name" {
  description = "Name of the isolated C2 GitHub Actions role."
  value       = aws_iam_role.c2.name
}

output "role_arn" {
  description = "ARN of the isolated C2 GitHub Actions role."
  value       = aws_iam_role.c2.arn
}

output "policy_arn" {
  description = "ARN of the isolated C2 GitHub Actions policy."
  value       = aws_iam_policy.c2.arn
}

output "github_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the C2 role."
  value       = local.github_subject
}
