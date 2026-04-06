variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "alb_sg_id" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
