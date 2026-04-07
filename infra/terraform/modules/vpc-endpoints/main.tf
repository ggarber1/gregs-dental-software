data "aws_region" "current" {}

# Security group for interface endpoints — allows inbound 443 from app tasks only
resource "aws_security_group" "endpoints" {
  name        = "dental-${var.env}-vpc-endpoints"
  description = "VPC interface endpoints - inbound 443 from app tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = var.app_sg_ids
    description     = "HTTPS from ECS tasks and workers"
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-vpc-endpoints-sg" })
}

# S3 gateway endpoint — free, required for ECR image layer pulls
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = merge(var.tags, { Name = "dental-${var.env}-s3-endpoint" })
}

# SSM — required for ECS agent to inject secrets from Parameter Store at task startup
resource "aws_vpc_endpoint" "ssm" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ssm"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "dental-${var.env}-ssm-endpoint" })
}

# ECR API — required for ECS agent to authenticate image pulls
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "dental-${var.env}-ecr-api-endpoint" })
}

# ECR DKR — required for Docker image layer pulls from ECR
resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "dental-${var.env}-ecr-dkr-endpoint" })
}

# CloudWatch Logs — required for ECS log driver to stream container logs
resource "aws_vpc_endpoint" "logs" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "dental-${var.env}-logs-endpoint" })
}
