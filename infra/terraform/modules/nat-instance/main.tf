# Staging-only: t4g.nano EC2 NAT instance. Stoppable, ~$1/mo at 10hrs/week.
# Production uses the nat-gateway module instead.

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_security_group" "nat" {
  name        = "dental-${var.env}-nat-instance"
  description = "NAT instance - allow private subnets outbound to internet"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.private_cidr_block]
    description = "All traffic from private subnets"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "dental-${var.env}-nat-instance-sg" })
}

resource "aws_instance" "nat" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = "t4g.nano"
  subnet_id                   = var.public_subnet_id
  vpc_security_group_ids      = [aws_security_group.nat.id]
  source_dest_check           = false
  associate_public_ip_address = true

  user_data = base64encode(<<-EOF
    #!/bin/bash
    # Enable IP forwarding permanently
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    sysctl -p

    # Detect the primary interface (AL2023 uses ens5, not eth0)
    PRIMARY_IF=$(ip route | awk '/default/ {print $5; exit}')

    # Create a proper systemd service using printf to avoid heredoc-in-heredoc issues.
    # rc-local has no [Install] section on AL2023 so systemctl enable rc-local
    # silently fails — iptables MASQUERADE rule was never re-applied after stop/start.
    printf '[Unit]\nDescription=NAT iptables MASQUERADE\nAfter=network.target\n\n[Service]\nType=oneshot\nExecStart=/bin/sh -c "iptables -t nat -C POSTROUTING -o %s -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -o %s -j MASQUERADE"\nRemainAfterExit=yes\n\n[Install]\nWantedBy=multi-user.target\n' \
      "$${PRIMARY_IF}" "$${PRIMARY_IF}" \
      > /etc/systemd/system/nat-masquerade.service

    systemctl daemon-reload
    systemctl enable nat-masquerade.service
    systemctl start nat-masquerade.service
    EOF
  )

  tags = merge(var.tags, {
    Name = "dental-${var.env}-nat-instance"
    Role = "nat"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route" "private_nat" {
  count                = length(var.private_route_table_ids)
  route_table_id       = var.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id = aws_instance.nat.primary_network_interface_id
}
