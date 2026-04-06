variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_id" {
  type = string
}

variable "private_route_table_ids" {
  type = list(string)
}

variable "private_cidr_block" {
  description = "CIDR block of private subnets — allowed inbound to NAT instance"
  type        = string
  default     = "10.0.0.0/8"
}

variable "tags" {
  type    = map(string)
  default = {}
}
