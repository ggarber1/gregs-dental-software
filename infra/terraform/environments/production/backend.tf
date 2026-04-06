terraform {
  backend "s3" {
    bucket         = "greg-dental-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    use_lockfile   = true
    encrypt        = true
  }
}
