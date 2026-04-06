variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Domain name for the application. Leave empty until a domain is chosen — ALB runs HTTP-only."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms and staging lifecycle notifications"
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
