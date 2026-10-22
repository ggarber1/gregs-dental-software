variable "env" {
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

variable "ecr_api_repo_url" {
  description = "ECR repository of the API image the workers run."
  type        = string
}

variable "image_tag" {
  description = "Initial image tag; the deploy workflow updates the functions afterwards."
  type        = string
}

variable "s3_bucket_names" {
  type = object({
    phi_documents = string
    era_files     = string
    exports       = string
  })
}

variable "tags" {
  type    = map(string)
  default = {}
}
