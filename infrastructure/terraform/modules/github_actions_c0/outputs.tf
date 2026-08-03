output "oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "role_name" {
  description = "Name of the isolated C0 GitHub Actions role."
  value       = aws_iam_role.c0.name
}

output "role_arn" {
  description = "ARN of the isolated C0 GitHub Actions role."
  value       = aws_iam_role.c0.arn
}

output "policy_arn" {
  description = "ARN of the isolated C0 GitHub Actions policy."
  value       = aws_iam_policy.c0.arn
}

output "github_subject" {
  description = "Exact immutable GitHub OIDC subject trusted by the role."
  value       = local.github_subject
}
