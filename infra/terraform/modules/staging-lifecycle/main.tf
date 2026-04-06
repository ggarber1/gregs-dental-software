data "archive_file" "handler" {
  type        = "zip"
  output_path = "${path.module}/lifecycle_handler.zip"
  source_file = "${path.module}/lambda/handler.py"
}

resource "aws_iam_role" "lifecycle" {
  name = "dental-${var.env}-lifecycle"

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

resource "aws_iam_role_policy" "lifecycle" {
  name = "dental-${var.env}-lifecycle"
  role = aws_iam_role.lifecycle.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:UpdateService",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["rds:DescribeDBInstances", "rds:StopDBInstance"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:StopInstances"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = var.alerts_topic_arn
      },
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

resource "aws_lambda_function" "lifecycle" {
  function_name    = "dental-${var.env}-staging-lifecycle"
  role             = aws_iam_role.lifecycle.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 60
  filename         = data.archive_file.handler.output_path
  source_code_hash = data.archive_file.handler.output_base64sha256

  environment {
    variables = {
      ECS_CLUSTER_ARN   = var.ecs_cluster_arn
      ECS_SERVICE_NAMES = join(",", var.ecs_service_names)
      RDS_INSTANCE_ID   = var.rds_instance_id
      NAT_INSTANCE_ID   = var.nat_instance_id
      SNS_TOPIC_ARN     = var.alerts_topic_arn
      ENV               = var.env
    }
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-staging-lifecycle" })
}

resource "aws_cloudwatch_log_group" "lifecycle" {
  name              = "/aws/lambda/dental-${var.env}-staging-lifecycle"
  retention_in_days = 30
  tags              = var.tags
}

# Midnight EST = 5 AM UTC
resource "aws_cloudwatch_event_rule" "midnight" {
  name                = "dental-${var.env}-midnight-lifecycle"
  description         = "Check for running staging resources at midnight and shut them down"
  schedule_expression = "cron(0 5 * * ? *)"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "midnight" {
  rule      = aws_cloudwatch_event_rule.midnight.name
  target_id = "lifecycle-lambda"
  arn       = aws_lambda_function.lifecycle.arn
}

resource "aws_lambda_permission" "midnight" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lifecycle.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.midnight.arn
}
