variable "env" {
  type = string
}

variable "cidr_block" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
