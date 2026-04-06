variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "api_task_sg_id" {
  type = string
}

variable "web_task_sg_id" {
  type = string
}

variable "alb_sg_id" {
  description = "ALB SG ID — not used for rules here (done in security-groups module) but kept for reference"
  type        = string
}

variable "api_target_group_arn" {
  type = string
}

variable "web_target_group_arn" {
  type = string
}

variable "ecr_api_repo_url" {
  type = string
}

variable "ecr_web_repo_url" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "ssm_parameter_path" {
  type = string
}

variable "phi_documents_bucket_arn" {
  type = string
}

variable "era_files_bucket_arn" {
  type = string
}

variable "exports_bucket_arn" {
  type = string
}

variable "sqs_queue_arns" {
  description = "SQS queue ARNs the API task can send messages to"
  type        = list(string)
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "web_desired_count" {
  type    = number
  default = 1
}

variable "tags" {
  type    = map(string)
  default = {}
}
