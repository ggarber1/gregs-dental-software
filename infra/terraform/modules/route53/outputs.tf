output "zone_id" {
  value = local.zone_id
}

output "name_servers" {
  description = "NS records to set at the domain registrar. Empty when using an existing zone."
  value       = var.create_zone ? aws_route53_zone.main[0].name_servers : []
}

# Gate downstream HTTPS resources on this output so they wait for cert validation.
# Value is the validated cert ARN, or "" when validation is skipped.
output "validated_acm_certificate_arn" {
  value = length(aws_acm_certificate_validation.cert) > 0 ? aws_acm_certificate_validation.cert[0].certificate_arn : ""
}
