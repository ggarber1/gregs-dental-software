# App-tier security groups are created here (not inside ecs/lambda-workers modules)
# to break the circular dependency: rds/elasticache need the SG IDs to allow
# inbound, while ecs/lambda-workers need them as their own SGs.

resource "aws_security_group" "api_task" {
  name        = "dental-${var.env}-api-task"
  description = "ECS Fargate API task - inbound from ALB on 8000, outbound all"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-api-task-sg" })
}

resource "aws_security_group_rule" "api_task_from_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = var.alb_sg_id
  security_group_id        = aws_security_group.api_task.id
  description              = "From ALB only"
}

resource "aws_security_group" "web_task" {
  name        = "dental-${var.env}-web-task"
  description = "ECS Fargate web task - inbound from ALB on 3000, outbound all"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-web-task-sg" })
}

resource "aws_security_group_rule" "web_task_from_alb" {
  type                     = "ingress"
  from_port                = 3000
  to_port                  = 3000
  protocol                 = "tcp"
  source_security_group_id = var.alb_sg_id
  security_group_id        = aws_security_group.web_task.id
  description              = "From ALB only"
}

resource "aws_security_group" "worker" {
  name        = "dental-${var.env}-worker"
  description = "Lambda workers - no inbound, outbound to data layer and AWS APIs"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-worker-sg" })
}
