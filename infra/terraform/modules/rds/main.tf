resource "aws_db_subnet_group" "main" {
  name       = "dental-${var.env}"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, { Name = "dental-${var.env}-db-subnet-group" })
}

resource "aws_security_group" "rds" {
  name        = "dental-${var.env}-rds"
  description = "RDS PostgreSQL - allow inbound from app and worker SGs only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_sg_ids
    description     = "PostgreSQL from app/worker SGs"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-rds-sg" })
}

resource "aws_db_instance" "main" {
  identifier        = "dental-${var.env}"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = var.instance_class
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = var.kms_key_arn

  db_name  = "dental"
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period   = 35
  backup_window             = "03:00-04:00"
  maintenance_window        = "Mon:04:00-Mon:05:00"
  delete_automated_backups  = false

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "dental-${var.env}-final-snapshot"

  performance_insights_enabled = true

  tags = merge(var.tags, { Name = "dental-${var.env}-postgres" })

  lifecycle {
    # password is rotated manually and stored in SSM — don't drift on it
    ignore_changes = [password]
  }
}
