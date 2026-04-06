output "api_task_sg_id" {
  value = aws_security_group.api_task.id
}

output "web_task_sg_id" {
  value = aws_security_group.web_task.id
}

output "worker_sg_id" {
  value = aws_security_group.worker.id
}
