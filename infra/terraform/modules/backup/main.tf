resource "aws_backup_vault" "main" {
  name        = "dental-${var.env}"
  kms_key_arn = var.kms_key_arn

  tags = merge(var.tags, { Name = "dental-${var.env}-backup-vault" })
}

resource "aws_backup_plan" "main" {
  name = "dental-${var.env}"

  rule {
    rule_name         = "daily-35-day-retention"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 2 * * ? *)" # 2 AM UTC daily

    lifecycle {
      delete_after = 35
    }
  }

  rule {
    rule_name         = "weekly-90-day-retention"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 3 ? * 1 *)" # 3 AM UTC every Sunday

    lifecycle {
      delete_after = 90
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "backup" {
  name = "dental-${var.env}-backup"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "backup.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_selection" "rds" {
  name         = "dental-${var.env}-rds"
  plan_id      = aws_backup_plan.main.id
  iam_role_arn = aws_iam_role.backup.arn

  resources = [var.rds_instance_arn]
}
