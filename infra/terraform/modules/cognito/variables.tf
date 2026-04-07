variable "env" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "mfa_configuration" {
  type        = string
  default     = "ON"
  description = "MFA requirement: ON (required), OPTIONAL, or OFF. Use OPTIONAL in staging for easier testing."
}
