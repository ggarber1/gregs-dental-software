variable "env" {
  type = string
}

variable "public_subnet_id" {
  type = string
}

variable "private_route_table_ids" {
  type = list(string)
}

variable "internet_gateway_id" {
  description = "IGW ID — ensures NAT gateway is created after the IGW"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
