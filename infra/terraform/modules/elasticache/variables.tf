variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "allowed_sg_ids" {
  description = "Security group IDs allowed to connect on port 6379"
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
