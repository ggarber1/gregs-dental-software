output "cluster_id" {
  value = aws_elasticache_cluster.main.cluster_id
}

output "endpoint" {
  value     = aws_elasticache_cluster.main.cache_nodes[0].address
  sensitive = true
}

output "port" {
  value = aws_elasticache_cluster.main.port
}

output "sg_id" {
  value = aws_security_group.redis.id
}
