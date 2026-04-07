locals {
  path = "/dental/${var.env}"
}

# Placeholder parameters — values are set manually after first apply.
# lifecycle ignore_changes = [value] prevents Terraform from overwriting manual updates.
# After first apply: populate each parameter in the AWS console or with aws ssm put-parameter.

resource "aws_ssm_parameter" "db_url" {
  name   = "${local.path}/db/url"
  type   = "SecureString"
  value  = "placeholder — set after first apply: postgresql://user:pass@host:5432/dental"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "redis_url" {
  name   = "${local.path}/redis/url"
  type   = "SecureString"
  value  = "placeholder — set after first apply: redis://host:6379"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "cognito_user_pool_id" {
  name  = "${local.path}/cognito/user_pool_id"
  type  = "String"
  value = "placeholder"
  tags  = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "cognito_app_client_id" {
  name  = "${local.path}/cognito/app_client_id"
  type  = "String"
  value = "placeholder"
  tags  = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "twilio_account_sid" {
  name   = "${local.path}/twilio/account_sid"
  type   = "SecureString"
  value  = "placeholder"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "twilio_auth_token" {
  name   = "${local.path}/twilio/auth_token"
  type   = "SecureString"
  value  = "placeholder"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "twilio_phone_number" {
  name   = "${local.path}/twilio/phone_number"
  type   = "SecureString"
  value  = "placeholder"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "clearinghouse_api_key" {
  name   = "${local.path}/clearinghouse/api_key"
  type   = "SecureString"
  value  = "placeholder"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "api_url" {
  name  = "${local.path}/app/api_url"
  type  = "String"
  value = "placeholder — set to public API URL e.g. https://api.staging.example.com"
  tags  = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "secret_key" {
  name   = "${local.path}/app/secret_key"
  type   = "SecureString"
  value  = "placeholder — set to a 64-char random hex string"
  key_id = var.kms_key_arn
  tags   = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

# IAM policy — read all parameters under /dental/{env}/
resource "aws_iam_policy" "ssm_read" {
  name        = "dental-${var.env}-ssm-read"
  description = "Read all SSM parameters under /dental/${var.env}/"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        Resource = "arn:aws:ssm:*:*:parameter${local.path}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = var.kms_key_arn
      },
    ]
  })

  tags = var.tags
}
