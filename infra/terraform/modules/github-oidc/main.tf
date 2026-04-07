data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# GitHub rotated their OIDC cert in 2023. Both thumbprints are included
# so the provider stays valid across cert rotations.
locals {
  github_thumbprints = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

# The OIDC provider is account-level. Only one environment should create it;
# others reference it via data source. Control with create_oidc_provider.
resource "aws_iam_openid_connect_provider" "github_actions" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = local.github_thumbprints
  tags            = var.tags
}

data "aws_iam_openid_connect_provider" "github_actions" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_provider_arn = var.create_oidc_provider \
    ? aws_iam_openid_connect_provider.github_actions[0].arn \
    : data.aws_iam_openid_connect_provider.github_actions[0].arn
}

resource "aws_iam_role" "github_actions" {
  name = "dental-${var.env}-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "github_actions" {
  name = "dental-${var.env}-github-actions"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ECR auth token — account-wide, cannot be resource-scoped
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      # ECR image push/pull for api and web repos
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
        ]
        Resource = [
          "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/dental/api",
          "arn:aws:ecr:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:repository/dental/web",
        ]
      },
      # ECS task definition registration — RegisterTaskDefinition is account-wide
      {
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
        Resource = "*"
      },
      # ECS service updates scoped to this environment's cluster
      {
        Effect = "Allow"
        Action = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:service/dental-${var.env}/*"
      },
      # ECS one-off migration task — RunTask scoped to api task definition
      {
        Effect  = "Allow"
        Action  = ["ecs:RunTask"]
        Resource = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task-definition/dental-${var.env}-api:*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:cluster/dental-${var.env}"
          }
        }
      },
      # ECS migration task lifecycle — DescribeTasks/StopTask scoped to cluster tasks
      {
        Effect   = "Allow"
        Action   = ["ecs:DescribeTasks", "ecs:StopTask"]
        Resource = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task/dental-${var.env}/*"
      },
      # IAM PassRole — allows ECS to assume task roles when running migration task
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/dental-${var.env}-task-execution",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/dental-${var.env}-api-task",
        ]
      },
      # CloudWatch Logs — read migration task output for debugging
      {
        Effect   = "Allow"
        Action   = ["logs:GetLogEvents", "logs:DescribeLogStreams"]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/dental/${var.env}/api:*"
      },
      # SSM — read build-time config (Cognito IDs, API URL) during web image build
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/dental/${var.env}/*"
      },
    ]
  })
}
