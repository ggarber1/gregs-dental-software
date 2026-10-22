output "reminders_function_name" {
  value = aws_lambda_function.worker["reminders"].function_name
}

output "risk_scoring_function_name" {
  value = aws_lambda_function.worker["risk-scoring"].function_name
}
