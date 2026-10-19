variable "env" {
  type = string
}

variable "domain_name" {
  description = "Zone apex (e.g., yourdomain.com or staging.yourdomain.com)."
  type        = string
}

variable "create_zone" {
  description = "Create a new hosted zone. Set false and pass existing_zone_id to manage records in a zone created elsewhere."
  type        = bool
  default     = true
}

variable "existing_zone_id" {
  description = "Zone ID when create_zone = false. Ignored otherwise."
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN to validate. Empty string skips validation."
  type        = string
  default     = ""
}

variable "acm_domain_validation_options" {
  description = "domain_validation_options from the aws_acm_certificate resource. Empty list skips validation."
  type = set(object({
    domain_name           = string
    resource_record_name  = string
    resource_record_type  = string
    resource_record_value = string
  }))
  default = []
}

variable "apex_alias" {
  description = "ALIAS record at the zone apex. Null to skip."
  type = object({
    dns_name = string
    zone_id  = string
  })
  default = null
}

variable "www_alias" {
  description = "ALIAS record at www.<domain_name>. Null to skip."
  type = object({
    dns_name = string
    zone_id  = string
  })
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
