output "distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "domain_name" {
  value = aws_cloudfront_distribution.main.domain_name
}

output "hosted_zone_id" {
  description = "CloudFront's fixed Route 53 zone ID for ALIAS records."
  value       = aws_cloudfront_distribution.main.hosted_zone_id
}
