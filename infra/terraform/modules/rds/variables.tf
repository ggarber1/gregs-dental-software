variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "kms_key_arn" {
  type = string
}

variable "db_username" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "allowed_sg_ids" {
  description = "Security group IDs allowed to connect on port 5432"
  type        = list(string)
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "tags" {
  type    = map(string)
  default = {}
}
