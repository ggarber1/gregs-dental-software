resource "aws_cognito_user_pool" "main" {
  name = "dental-${var.env}"

  # TOTP MFA — ON in production, OPTIONAL in staging for easier testing
  mfa_configuration = var.mfa_configuration

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Admin-only user creation — no self-signup
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  # practice_id and role stored as custom attributes on the Cognito user
  schema {
    name                = "practice_id"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 36
    }
  }

  schema {
    name                = "role"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {
      min_length = 1
      max_length = 50
    }
  }

  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  tags = var.tags
}

# SPA client — no secret, SRP auth only
resource "aws_cognito_user_pool_client" "web" {
  name         = "dental-${var.env}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  prevent_user_existence_errors = "ENABLED"
}
