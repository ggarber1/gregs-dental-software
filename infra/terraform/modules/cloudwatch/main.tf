resource "aws_sns_topic" "alerts" {
  name              = "dental-${var.env}-alerts"
  kms_master_key_id = "alias/aws/sns"
  tags              = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ALB 5xx errors
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "dental-${var.env}-alb-5xx-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "ALB 5xx errors > 10/min for 2 consecutive minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# RDS CPU
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "dental-${var.env}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU > 80% for 15 minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# RDS free storage
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "dental-${var.env}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5368709120 # 5 GB in bytes
  alarm_description   = "RDS free storage < 5GB — expand allocated storage soon"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# DLQ depth — any message in a DLQ means a worker failed max_receive_count times
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = {
    reminders   = var.reminders_dlq_name
    eligibility = var.eligibility_dlq_name
    era         = var.era_dlq_name
  }

  alarm_name          = "dental-${var.env}-${each.key}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "${each.key} DLQ has messages — investigate worker failures immediately"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# Lambda worker error rates
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    reminder    = var.reminder_worker_fn
    eligibility = var.eligibility_worker_fn
    era         = var.era_worker_fn
  }

  alarm_name          = "dental-${var.env}-${each.key}-worker-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "${each.key} worker > 5 errors in 10 minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# ElastiCache CPU — uses notBreaching so staging-down (ElastiCache deleted) doesn't fire
resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  alarm_name          = "dental-${var.env}-redis-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 70
  alarm_description   = "Redis CPU > 70% for 15 minutes"
  treat_missing_data  = "notBreaching"

  dimensions = {
    CacheClusterId = var.elasticache_cluster_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}
