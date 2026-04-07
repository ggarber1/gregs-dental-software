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

    # Write masquerade rule to rc.local so it runs on every boot
    echo '#!/bin/bash' > /etc/rc.d/rc.local
    echo 'iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE' >> /etc/rc.d/rc.local
    chmod +x /etc/rc.d/rc.local
    systemctl enable rc-local

    # Apply immediately without waiting for reboot
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
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
