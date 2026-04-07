variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "private_route_table_ids" {
  type = list(string)
}

variable "app_sg_ids" {
  description = "Security group IDs for ECS tasks and workers — these need to reach the endpoints"
  type        = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
