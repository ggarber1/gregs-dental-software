output "alb_arn" {
  value = aws_lb.main.arn
}

output "alb_arn_suffix" {
  value = aws_lb.main.arn_suffix
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "alb_zone_id" {
  value = aws_lb.main.zone_id
}

output "alb_sg_id" {
  value = aws_security_group.alb.id
}

output "api_target_group_arn" {
  value = aws_lb_target_group.api.arn
}

output "api_target_group_arn_suffix" {
  value = aws_lb_target_group.api.arn_suffix
}

output "web_target_group_arn" {
  value = aws_lb_target_group.web.arn
}

output "acm_certificate_arn" {
  description = "Unvalidated ACM cert ARN. Empty when domain_name is unset."
  value       = length(aws_acm_certificate.main) > 0 ? aws_acm_certificate.main[0].arn : ""
}

output "acm_domain_validation_options" {
  description = "Pass to route53 module to create DNS validation records."
  value       = length(aws_acm_certificate.main) > 0 ? aws_acm_certificate.main[0].domain_validation_options : []
}
