output "instance_id" {
  value = aws_instance.whisper.id
}

output "private_ip" {
  description = "Private IP of the Whisper EC2 — use this to populate the whisper/endpoint_url SSM parameter"
  value       = aws_instance.whisper.private_ip
}

output "whisper_sg_id" {
  value = aws_security_group.whisper.id
}
