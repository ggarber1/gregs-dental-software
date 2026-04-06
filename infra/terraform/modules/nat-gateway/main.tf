# Production-only: managed NAT Gateway. Always-on, ~$32/mo.
# Staging uses the nat-instance module instead.

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = merge(var.tags, { Name = "dental-${var.env}-nat-eip" })
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = var.public_subnet_id

  tags = merge(var.tags, { Name = "dental-${var.env}-nat-gw" })

  depends_on = [var.internet_gateway_id]
}

resource "aws_route" "private_nat" {
  count                  = length(var.private_route_table_ids)
  route_table_id         = var.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main.id
}
