variable "env" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "alb_arn_suffix" {
  type = string
}

variable "api_target_group_arn_suffix" {
  type = string
}

variable "rds_instance_id" {
  type = string
}

variable "elasticache_cluster_id" {
  type = string
}

variable "reminders_dlq_name" {
  type = string
}

variable "eligibility_dlq_name" {
  type = string
}

variable "era_dlq_name" {
  type = string
}

variable "reminder_worker_fn" {
  type = string
}

variable "eligibility_worker_fn" {
  type = string
}

variable "era_worker_fn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
