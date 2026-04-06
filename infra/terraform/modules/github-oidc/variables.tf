variable "env" {
  type        = string
  description = "Environment name (staging or production)"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository in owner/name format"
}

variable "create_oidc_provider" {
  type        = bool
  default     = true
  description = "Create the GitHub OIDC provider. Set false if already created by another environment in the same account."
}

variable "tags" {
  type    = map(string)
  default = {}
}
