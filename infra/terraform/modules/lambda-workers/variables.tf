variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "worker_sg_id" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "ssm_parameter_path" {
  type = string
}

variable "reminders_queue_arn" {
  type = string
}

variable "eligibility_queue_arn" {
  type = string
}

variable "era_queue_arn" {
  type = string
}

variable "phi_documents_bucket_arn" {
  type = string
}

variable "era_files_bucket_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
