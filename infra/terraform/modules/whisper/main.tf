data "aws_region" "current" {}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── Security group ─────────────────────────────────────────────────────────────

resource "aws_security_group" "whisper" {
  name        = "dental-${var.env}-whisper"
  description = "Whisper EC2 - inbound from API ECS task on 8080, outbound all"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [var.api_task_sg_id]
    description     = "API ECS task to Whisper"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "ECR pull, CloudWatch, SSM"
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-whisper-sg" })
}

# ── IAM ───────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "whisper" {
  name = "dental-${var.env}-whisper"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "whisper" {
  name = "dental-${var.env}-whisper"
  role = aws_iam_role.whisper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = var.ecr_whisper_repo_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "${aws_cloudwatch_log_group.whisper.arn}:*"
      },
    ]
  })
}

# SSM Session Manager — SSH-free access for debugging
resource "aws_iam_role_policy_attachment" "whisper_ssm" {
  role       = aws_iam_role.whisper.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "whisper" {
  name = "dental-${var.env}-whisper"
  role = aws_iam_role.whisper.name
  tags = var.tags
}

# ── CloudWatch log group ───────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "whisper" {
  name              = "/dental/${var.env}/whisper"
  retention_in_days = 30
  tags              = var.tags
}

# ── EC2 instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "whisper" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.large" # 2 vCPU, 8 GB — sufficient for large-v3-turbo on CPU
  subnet_id              = var.private_subnet_id
  vpc_security_group_ids = [aws_security_group.whisper.id]
  iam_instance_profile   = aws_iam_instance_profile.whisper.name

  root_block_device {
    volume_size = 30 # OS + Docker + model cache (~1.5 GB for large-v3-turbo)
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    ecr_repo_url  = var.ecr_whisper_repo_url
    aws_region    = data.aws_region.current.name
    whisper_model = "large-v3-turbo"
  }))

  metadata_options {
    http_tokens   = "required" # IMDSv2 only
    http_endpoint = "enabled"
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-whisper" })
}
