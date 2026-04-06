output "reminder_function_name" {
  value = aws_lambda_function.worker["reminder"].function_name
}

output "eligibility_function_name" {
  value = aws_lambda_function.worker["eligibility"].function_name
}

output "era_function_name" {
  value = aws_lambda_function.worker["era"].function_name
}
