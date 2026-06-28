output "key_vault_uri" {
  description = "URI of the Azure Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "acr_login_server" {
  description = "Login server URL for the container registry"
  value       = module.acr.login_server
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
  description = "Full PostgreSQL connection string (sensitive)"
  value       = module.postgres.database_url
  sensitive   = true
}

output "redis_url" {
  description = "Full Redis connection string (sensitive)"
  value       = module.redis.redis_url
  sensitive   = true
}
