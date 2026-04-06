output "alb_dns_name" {
  description = "ALB DNS name"
  value       = module.alb.alb_dns_name
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name"
  value       = module.cloudfront.domain_name
}

output "ecr_api_repo_url" {
  description = "ECR URL for the api image"
  value       = module.ecr.api_repo_url
}

output "ecr_web_repo_url" {
  description = "ECR URL for the web image"
  value       = module.ecr.web_repo_url
}

output "rds_endpoint" {
  description = "RDS endpoint — populate SSM /dental/production/db/url after first apply"
  value       = module.rds.endpoint
  sensitive   = true
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_app_client_id" {
  value = module.cognito.app_client_id
}
