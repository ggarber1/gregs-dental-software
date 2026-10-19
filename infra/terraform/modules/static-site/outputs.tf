output "bucket_name" {
  value = aws_s3_bucket.site.id
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_hosted_zone_id" {
  description = "CloudFront's fixed Route 53 zone ID for ALIAS records."
  value       = aws_cloudfront_distribution.site.hosted_zone_id
}
