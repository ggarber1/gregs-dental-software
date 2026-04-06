locals {
  worker_queues = {
    reminders = {
      visibility_timeout = 300 # 5 min — matches Lambda timeout
      max_receive_count  = 3
    }
    eligibility = {
      visibility_timeout = 300
      max_receive_count  = 3
    }
    era = {
      visibility_timeout = 300
      max_receive_count  = 3
    }
  }
}

# Dead-letter queues — created first, referenced by main queue redrive policies
resource "aws_sqs_queue" "dlq" {
  for_each = local.worker_queues

  name                      = "dental-${each.key}-dlq-${var.env}"
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = "alias/aws/sqs"

  tags = merge(var.tags, { Name = "dental-${each.key}-dlq-${var.env}" })
}

# Worker queues with DLQ redrive after max_receive_count failures
resource "aws_sqs_queue" "worker" {
  for_each = local.worker_queues

  name                       = "dental-${each.key}-queue-${var.env}"
  visibility_timeout_seconds = each.value.visibility_timeout
  message_retention_seconds  = 345600 # 4 days
  kms_master_key_id          = "alias/aws/sqs"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.max_receive_count
  })

  tags = merge(var.tags, { Name = "dental-${each.key}-queue-${var.env}" })
}

# Audit-logs queue — best-effort, no DLQ
resource "aws_sqs_queue" "audit_logs" {
  name                       = "dental-audit-logs-queue-${var.env}"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400 # 1 day
  kms_master_key_id          = "alias/aws/sqs"

  tags = merge(var.tags, { Name = "dental-audit-logs-queue-${var.env}" })
}
