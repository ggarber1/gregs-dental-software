variable "env" {
  type = string
}

variable "bucket_name" {
  description = "S3 bucket name. Must be globally unique."
  type        = string
}

variable "aliases" {
  description = "CNAME aliases for the CloudFront distribution (e.g., [\"yourdomain.com\", \"www.yourdomain.com\"]). Empty list runs without a custom domain."
  type        = list(string)
  default     = []
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN (must be in us-east-1) covering all aliases. Empty = use CloudFront default cert."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
