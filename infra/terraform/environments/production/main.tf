locals {
  env    = "production"
  prefix = "dental-${local.env}"

  common_tags = {
    Project     = "dental-pms"
    Environment = local.env
  }
}

module "kms" {
  source = "../../modules/kms"
  env    = local.env
  tags   = local.common_tags
}

module "vpc" {
  source             = "../../modules/vpc"
  env                = local.env
  cidr_block         = "10.1.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  tags               = local.common_tags
}

# Production: managed NAT Gateway (always-on, ~$32/mo)
# Staging uses nat-instance module instead
module "nat_gateway" {
  source                  = "../../modules/nat-gateway"
  env                     = local.env
  public_subnet_id        = module.vpc.public_subnet_ids[0]
  private_route_table_ids = module.vpc.private_route_table_ids
  internet_gateway_id     = module.vpc.internet_gateway_id
  tags                    = local.common_tags
}

module "s3" {
  source      = "../../modules/s3"
  env         = local.env
  kms_key_arn = module.kms.key_arn
  tags        = local.common_tags
}

module "sqs" {
  source = "../../modules/sqs"
  env    = local.env
  tags   = local.common_tags
}

module "cognito" {
  source = "../../modules/cognito"
  env    = local.env
  tags   = local.common_tags
}

module "ecr" {
  source = "../../modules/ecr"
  env    = local.env
  tags   = local.common_tags
}

module "ssm" {
  source      = "../../modules/ssm"
  env         = local.env
  kms_key_arn = module.kms.key_arn
  tags        = local.common_tags
}

module "alb" {
  source                     = "../../modules/alb"
  env                        = local.env
  vpc_id                     = module.vpc.vpc_id
  public_subnet_ids          = module.vpc.public_subnet_ids
  domain_name                = var.domain_name
  enable_deletion_protection = true
  tags                       = local.common_tags
}

module "security_groups" {
  source    = "../../modules/security-groups"
  env       = local.env
  vpc_id    = module.vpc.vpc_id
  alb_sg_id = module.alb.alb_sg_id
  tags      = local.common_tags
}

module "rds" {
  source      = "../../modules/rds"
  env         = local.env
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = module.kms.key_arn
  db_username = var.db_username
  db_password = var.db_password
  allowed_sg_ids = [
    module.security_groups.api_task_sg_id,
    module.security_groups.worker_sg_id,
  ]
  tags = local.common_tags
}

module "elasticache" {
  source     = "../../modules/elasticache"
  env        = local.env
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
  allowed_sg_ids = [
    module.security_groups.api_task_sg_id,
    module.security_groups.worker_sg_id,
  ]
  tags = local.common_tags
}

module "ecs" {
  source               = "../../modules/ecs"
  env                  = local.env
  vpc_id               = module.vpc.vpc_id
  private_subnet_ids   = module.vpc.private_subnet_ids
  api_task_sg_id       = module.security_groups.api_task_sg_id
  web_task_sg_id       = module.security_groups.web_task_sg_id
  alb_sg_id            = module.alb.alb_sg_id
  api_target_group_arn = module.alb.api_target_group_arn
  web_target_group_arn = module.alb.web_target_group_arn
  ecr_api_repo_url     = module.ecr.api_repo_url
  ecr_web_repo_url     = module.ecr.web_repo_url
  kms_key_arn          = module.kms.key_arn
  ssm_parameter_path   = module.ssm.parameter_path_prefix
  phi_documents_bucket_arn = module.s3.phi_documents_bucket_arn
  era_files_bucket_arn     = module.s3.era_files_bucket_arn
  exports_bucket_arn       = module.s3.exports_bucket_arn
  sqs_queue_arns = [
    module.sqs.reminders_queue_arn,
    module.sqs.eligibility_queue_arn,
    module.sqs.era_queue_arn,
    module.sqs.audit_logs_queue_arn,
  ]
  api_desired_count = 1
  web_desired_count = 1
  tags              = local.common_tags
}

module "lambda_workers" {
  source             = "../../modules/lambda-workers"
  env                = local.env
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  worker_sg_id       = module.security_groups.worker_sg_id
  kms_key_arn        = module.kms.key_arn
  ssm_parameter_path = module.ssm.parameter_path_prefix
  reminders_queue_arn      = module.sqs.reminders_queue_arn
  eligibility_queue_arn    = module.sqs.eligibility_queue_arn
  era_queue_arn            = module.sqs.era_queue_arn
  phi_documents_bucket_arn = module.s3.phi_documents_bucket_arn
  era_files_bucket_arn     = module.s3.era_files_bucket_arn
  tags               = local.common_tags
}

# Production-only: WAF attached to ALB
module "waf" {
  source  = "../../modules/waf"
  env     = local.env
  alb_arn = module.alb.alb_arn
  tags    = local.common_tags
}

# Production-only: CloudFront CDN
module "cloudfront" {
  source              = "../../modules/cloudfront"
  env                 = local.env
  alb_dns_name        = module.alb.alb_dns_name
  domain_name         = var.domain_name
  waf_web_acl_arn     = module.waf.web_acl_arn
  tags                = local.common_tags
}

module "cloudwatch" {
  source                      = "../../modules/cloudwatch"
  env                         = local.env
  alert_email                 = var.alert_email
  alb_arn_suffix              = module.alb.alb_arn_suffix
  api_target_group_arn_suffix = module.alb.api_target_group_arn_suffix
  rds_instance_id             = module.rds.instance_id
  elasticache_cluster_id      = module.elasticache.cluster_id
  reminders_dlq_name          = module.sqs.reminders_dlq_name
  eligibility_dlq_name        = module.sqs.eligibility_dlq_name
  era_dlq_name                = module.sqs.era_dlq_name
  reminder_worker_fn          = module.lambda_workers.reminder_function_name
  eligibility_worker_fn       = module.lambda_workers.eligibility_function_name
  era_worker_fn               = module.lambda_workers.era_function_name
  tags                        = local.common_tags
}

module "backup" {
  source           = "../../modules/backup"
  env              = local.env
  kms_key_arn      = module.kms.key_arn
  rds_instance_arn = module.rds.instance_arn
  tags             = local.common_tags
}

# No staging_lifecycle module in production
