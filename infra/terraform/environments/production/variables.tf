variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Domain name for the application. Required for production HTTPS."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms"
  type        = string
}

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "dental_admin"
}

variable "db_password" {
  description = "RDS master password — stored in SSM after first apply, not kept in state"
  type        = string
  sensitive   = true
}
