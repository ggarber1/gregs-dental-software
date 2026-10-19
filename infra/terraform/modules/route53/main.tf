resource "aws_route53_zone" "main" {
  count = var.create_zone ? 1 : 0
  name  = var.domain_name

  tags = merge(var.tags, { Name = "dental-${var.env}-zone" })
}

locals {
  zone_id = var.create_zone ? aws_route53_zone.main[0].zone_id : var.existing_zone_id
}

# Key on domain_name (known at plan time) rather than resource_record_name
# (known after apply). Wildcard + apex SAN pairs produce the same underlying
# Route 53 record — allow_overwrite makes that idempotent.
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in var.acm_domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id         = local.zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.value]
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cert" {
  count = var.acm_certificate_arn != "" && length(var.acm_domain_validation_options) > 0 ? 1 : 0

  certificate_arn         = var.acm_certificate_arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

resource "aws_route53_record" "apex_alias" {
  count = var.apex_alias != null ? 1 : 0

  zone_id = local.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = var.apex_alias.dns_name
    zone_id                = var.apex_alias.zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "www_alias" {
  count = var.www_alias != null ? 1 : 0

  zone_id = local.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.www_alias.dns_name
    zone_id                = var.www_alias.zone_id
    evaluate_target_health = false
  }
}
