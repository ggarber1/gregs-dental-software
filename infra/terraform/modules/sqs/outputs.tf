output "reminders_queue_arn" {
  value = aws_sqs_queue.worker["reminders"].arn
}

output "reminders_queue_url" {
  value = aws_sqs_queue.worker["reminders"].url
}

output "eligibility_queue_arn" {
  value = aws_sqs_queue.worker["eligibility"].arn
}

output "eligibility_queue_url" {
  value = aws_sqs_queue.worker["eligibility"].url
}

output "era_queue_arn" {
  value = aws_sqs_queue.worker["era"].arn
}

output "era_queue_url" {
  value = aws_sqs_queue.worker["era"].url
}

output "audit_logs_queue_arn" {
  value = aws_sqs_queue.audit_logs.arn
}

output "audit_logs_queue_url" {
  value = aws_sqs_queue.audit_logs.url
}

output "reminders_dlq_arn" {
  value = aws_sqs_queue.dlq["reminders"].arn
}

output "reminders_dlq_name" {
  value = aws_sqs_queue.dlq["reminders"].name
}

output "eligibility_dlq_arn" {
  value = aws_sqs_queue.dlq["eligibility"].arn
}

output "eligibility_dlq_name" {
  value = aws_sqs_queue.dlq["eligibility"].name
}

output "era_dlq_arn" {
  value = aws_sqs_queue.dlq["era"].arn
}

output "era_dlq_name" {
  value = aws_sqs_queue.dlq["era"].name
}
