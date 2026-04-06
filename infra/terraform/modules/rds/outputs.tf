output "instance_id" {
  value = aws_db_instance.main.id
}

output "instance_arn" {
  value = aws_db_instance.main.arn
}

output "endpoint" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}

output "sg_id" {
  value = aws_security_group.rds.id
}
