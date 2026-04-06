variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "domain_name" {
  description = "Domain name. Empty = HTTP-only listener, no ACM cert."
  type        = string
  default     = ""
}

variable "enable_deletion_protection" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
