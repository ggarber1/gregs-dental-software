output "role_arn" {
  description = "IAM role ARN for GitHub Actions — set as AWS_ACCOUNT_ID secret in repo settings"
  value       = aws_iam_role.github_actions.arn
}
