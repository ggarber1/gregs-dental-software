variable "env" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "rds_instance_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
