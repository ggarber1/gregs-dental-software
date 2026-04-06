output "parameter_path_prefix" {
  value = "/dental/${var.env}"
}

output "ssm_read_policy_arn" {
  value = aws_iam_policy.ssm_read.arn
}
