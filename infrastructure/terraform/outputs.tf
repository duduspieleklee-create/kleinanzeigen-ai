output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "acr_login_server" {
  description = "Login server URL for the container registry"
  value       = module.acr.login_server
}

output "acr_admin_username" {
  description = "Admin username for the container registry"
  value       = module.acr.admin_username
}

output "acr_admin_password" {
  description = "Admin password for the container registry (sensitive)"
  value       = module.acr.admin_password
  sensitive   = true
}

output "postgres_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL server"
  value       = module.postgres.fqdn
}

output "redis_hostname" {
  description = "Hostname of the Redis cache"
  value       = module.redis.hostname
}

output "database_url" {
  description = "Full PostgreSQL connection string — copy this as DATABASE_URL GitHub secret"
  value       = module.postgres.database_url
  sensitive   = true
}

output "redis_url" {
  description = "Full Redis connection URL with TLS — copy this as REDIS_URL GitHub secret"
  value       = module.redis.redis_url
  sensitive   = true
}
