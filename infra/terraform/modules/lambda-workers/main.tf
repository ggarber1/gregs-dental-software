data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Scheduled workers. Both run the API container image (awslambdaric entry point);
# image_config.command picks the handler in app/workers/lambda_handlers.py.
locals {
  functions = {
    reminders = {
      handler     = "app.workers.lambda_handlers.reminders"
      schedule    = "rate(15 minutes)"
      description = "Send appointment reminders that are due"
    }
    risk-scoring = {
      handler     = "app.workers.lambda_handlers.risk_scoring"
      schedule    = "cron(0 7 * * ? *)" # 2am ET
      description = "Score no-show risk for the next 7 days"
    }
  }
  ssm_path_arn = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_path}"
}

resource "aws_iam_role" "worker" {
  name = "dental-${var.env}-worker"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "worker_vpc" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "worker" {
  name = "dental-${var.env}-worker"
  role = aws_iam_role.worker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Cold-start settings load (app/core/lambda_config.py). GetParametersByPath
        # authorizes against the path itself; GetParameter against children.
        Effect   = "Allow"
        Action   = ["ssm:GetParametersByPath", "ssm:GetParameter", "ssm:GetParameters"]
        Resource = [local.ssm_path_arn, "${local.ssm_path_arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = var.kms_key_arn
      },
      {
        # Email reminders (app/services/email.py → SES SendEmail).
        Effect   = "Allow"
        Action   = ["ses:SendEmail"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "worker" {
  for_each = local.functions

  name              = "/aws/lambda/dental-${each.key}-worker-${var.env}"
  retention_in_days = 90
  tags              = var.tags
}

resource "aws_lambda_function" "worker" {
  for_each = local.functions

  function_name = "dental-${each.key}-worker-${var.env}"
  description   = each.value.description
  role          = aws_iam_role.worker.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_api_repo_url}:${var.image_tag}"
  architectures = ["x86_64"]
  timeout       = 300
  memory_size   = 512

  image_config {
    entry_point = ["python", "-m", "awslambdaric"]
    command     = [each.value.handler]
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.worker_sg_id]
  }

  # Non-secret settings only; secrets are read from SSM at cold start. Names match
  # app/core/config.py, which refuses to start in staging/production without them.
  environment {
    variables = {
      API_ENV                 = var.env
      SSM_PARAMETER_PATH      = var.ssm_parameter_path
      S3_BUCKET_PHI_DOCUMENTS = var.s3_bucket_names.phi_documents
      S3_BUCKET_ERA_FILES     = var.s3_bucket_names.era_files
      S3_BUCKET_EXPORTS       = var.s3_bucket_names.exports
    }
  }

  # The deploy workflow points the functions at each new image.
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.worker]

  tags = merge(var.tags, { Name = "dental-${each.key}-worker-${var.env}" })
}

resource "aws_cloudwatch_event_rule" "worker" {
  for_each = local.functions

  name                = "dental-${each.key}-${var.env}"
  description         = each.value.description
  schedule_expression = each.value.schedule
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "worker" {
  for_each = local.functions

  rule      = aws_cloudwatch_event_rule.worker[each.key].name
  target_id = "${each.key}-lambda"
  arn       = aws_lambda_function.worker[each.key].arn
}

resource "aws_lambda_permission" "worker_eventbridge" {
  for_each = local.functions

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.worker[each.key].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.worker[each.key].arn
}
