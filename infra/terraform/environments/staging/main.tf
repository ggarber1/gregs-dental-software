locals {
  env    = "staging"
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
  cidr_block         = "10.0.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b"]
  tags               = local.common_tags
}

# Staging: stoppable t4g.nano NAT instance (~$0 when stopped)
# Production uses nat-gateway module instead
module "nat_instance" {
  source                  = "../../modules/nat-instance"
  env                     = local.env
  vpc_id                  = module.vpc.vpc_id
  public_subnet_id        = module.vpc.public_subnet_ids[0]
  private_route_table_ids = module.vpc.private_route_table_ids
  private_cidr_block      = module.vpc.vpc_cidr_block
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
  source            = "../../modules/alb"
  env               = local.env
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  domain_name       = var.domain_name
  # No deletion protection in staging — easier to tear down
  enable_deletion_protection = false
  tags              = local.common_tags
}

# App-tier security groups created here to break the circular dependency:
# rds/elasticache need the SG IDs to allow inbound, but ecs/lambda-workers
# need to own those SGs. Creating them separately means no module depends
# on the output of another module that needs it first.
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

# ElastiCache is destroyed on staging-down and recreated on staging-up
# to save $12/mo. See Makefile targets.
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
  source              = "../../modules/ecs"
  env                 = local.env
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  api_task_sg_id      = module.security_groups.api_task_sg_id
  web_task_sg_id      = module.security_groups.web_task_sg_id
  alb_sg_id           = module.alb.alb_sg_id
  api_target_group_arn = module.alb.api_target_group_arn
  web_target_group_arn = module.alb.web_target_group_arn
  ecr_api_repo_url    = module.ecr.api_repo_url
  ecr_web_repo_url    = module.ecr.web_repo_url
  kms_key_arn         = module.kms.key_arn
  ssm_parameter_path  = module.ssm.parameter_path_prefix
  phi_documents_bucket_arn = module.s3.phi_documents_bucket_arn
  era_files_bucket_arn     = module.s3.era_files_bucket_arn
  exports_bucket_arn       = module.s3.exports_bucket_arn
  sqs_queue_arns = [
    module.sqs.reminders_queue_arn,
    module.sqs.eligibility_queue_arn,
    module.sqs.era_queue_arn,
    module.sqs.audit_logs_queue_arn,
  ]
  # Start at 0 — use make staging-up to bring services up
  api_desired_count = 0
  web_desired_count = 0
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
  reminders_queue_arn   = module.sqs.reminders_queue_arn
  eligibility_queue_arn = module.sqs.eligibility_queue_arn
  era_queue_arn         = module.sqs.era_queue_arn
  phi_documents_bucket_arn = module.s3.phi_documents_bucket_arn
  era_files_bucket_arn     = module.s3.era_files_bucket_arn
  tags               = local.common_tags
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

# GitHub Actions OIDC — create the provider here (account-level, one per account)
# Production sets create_oidc_provider = false and references this one via data source
module "github_oidc" {
  source               = "../../modules/github-oidc"
  env                  = local.env
  github_repo          = "ggarber1/gregs-dental-software"
  create_oidc_provider = true
  tags                 = local.common_tags
}

# Staging-only: midnight Lambda that stops anything left running and emails you
module "staging_lifecycle" {
  source            = "../../modules/staging-lifecycle"
  env               = local.env
  ecs_cluster_arn   = module.ecs.cluster_arn
  ecs_service_names = [module.ecs.api_service_name, module.ecs.web_service_name]
  rds_instance_id   = module.rds.instance_id
  nat_instance_id   = module.nat_instance.instance_id
  alerts_topic_arn  = module.cloudwatch.alerts_topic_arn
  tags              = local.common_tags
}
