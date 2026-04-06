variable "env" {
  type = string
}

variable "ecs_cluster_arn" {
  type = string
}

variable "ecs_service_names" {
  type = list(string)
}

variable "rds_instance_id" {
  type = string
}

variable "nat_instance_id" {
  type = string
}

variable "alerts_topic_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
