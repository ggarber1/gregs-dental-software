variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_id" {
  description = "Single private subnet to place the Whisper EC2 in"
  type        = string
}

variable "api_task_sg_id" {
  description = "Security group of the API ECS tasks — allowed to reach Whisper on port 8080"
  type        = string
}

variable "ecr_whisper_repo_url" {
  type = string
}

variable "ecr_whisper_repo_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
