resource "aws_elasticache_subnet_group" "main" {
  name       = "dental-${var.env}"
  subnet_ids = var.subnet_ids

  tags = var.tags
}

resource "aws_security_group" "redis" {
  name        = "dental-${var.env}-redis"
  description = "ElastiCache Redis - allow inbound from app and worker SGs only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.allowed_sg_ids
    description     = "Redis from app/worker SGs"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-redis-sg" })
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "dental-${var.env}"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  snapshot_retention_limit = 1
  snapshot_window          = "05:00-06:00"

  tags = merge(var.tags, { Name = "dental-${var.env}-redis" })
}
