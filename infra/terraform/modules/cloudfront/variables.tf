variable "env" {
  type = string
}

variable "alb_dns_name" {
  type = string
}

variable "domain_name" {
  type    = string
  default = ""
}

variable "acm_certificate_arn" {
  type    = string
  default = ""
}

variable "waf_web_acl_arn" {
  type    = string
  default = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
