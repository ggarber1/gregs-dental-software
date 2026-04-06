resource "aws_kms_key" "main" {
  description             = "dental-pms ${var.env} CMK — shared across RDS, S3, SSM"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "dental-${var.env}-cmk"
  })
}

resource "aws_kms_alias" "main" {
  name          = "alias/dental-${var.env}"
  target_key_id = aws_kms_key.main.key_id
}
