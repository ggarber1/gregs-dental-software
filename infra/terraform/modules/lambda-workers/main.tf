data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  workers = {
    reminder = {
      queue_arn  = var.reminders_queue_arn
      batch_size = 10
    }
    eligibility = {
      queue_arn  = var.eligibility_queue_arn
      batch_size = 5
    }
    era = {
      queue_arn  = var.era_queue_arn
      batch_size = 1 # ERA files are large — one at a time
    }
  }
}

# Shared IAM execution role for all three workers
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
        Effect = "Allow"
        Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [
          var.reminders_queue_arn,
          var.eligibility_queue_arn,
          var.era_queue_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject"]
        Resource = [
          "${var.phi_documents_bucket_arn}/*",
          "${var.era_files_bucket_arn}/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_parameter_path}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = var.kms_key_arn
      },
    ]
  })
}

# Placeholder ZIP for initial deployment — CI/CD replaces with real code
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = "def handler(event, context): raise Exception('placeholder — deploy real code via CI/CD')"
    filename = "handler.py"
  }
}

resource "aws_lambda_function" "worker" {
  for_each = local.workers

  function_name = "dental-${each.key}-worker-${var.env}"
  role          = aws_iam_role.worker.arn
  runtime       = "python3.12"
  handler       = "app.handler.handler"
  timeout       = 300
  memory_size   = 256

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.worker_sg_id]
  }

  environment {
    variables = {
      ENV                = var.env
      SSM_PARAMETER_PATH = var.ssm_parameter_path
    }
  }

  # CI/CD owns code updates after initial creation
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = merge(var.tags, { Name = "dental-${each.key}-worker-${var.env}" })
}

resource "aws_cloudwatch_log_group" "worker" {
  for_each = local.workers

  name              = "/aws/lambda/dental-${each.key}-worker-${var.env}"
  retention_in_days = 90
  tags              = var.tags
}

resource "aws_lambda_event_source_mapping" "worker" {
  for_each = local.workers

  event_source_arn = each.value.queue_arn
  function_name    = aws_lambda_function.worker[each.key].arn
  batch_size       = each.value.batch_size
  enabled          = true

  # Report individual item failures back to SQS so only failed messages go to DLQ
  function_response_types = ["ReportBatchItemFailures"]
}
