output "hostname" {
  description = "Hostname of the Redis cache"
  value       = azurerm_redis_cache.redis.hostname
}

output "ssl_port" {
  description = "SSL port (6380 — always use this, not the non-SSL port)"
  value       = azurerm_redis_cache.redis.ssl_port
}

output "primary_access_key" {
  description = "Primary access key for the Redis cache (sensitive)"
  value       = azurerm_redis_cache.redis.primary_access_key
  sensitive   = true
}

output "redis_url" {
  description = "Full Redis connection URL with TLS (sensitive) — use this as REDIS_URL"
  value       = "rediss://:${azurerm_redis_cache.redis.primary_access_key}@${azurerm_redis_cache.redis.hostname}:${azurerm_redis_cache.redis.ssl_port}/0"
  sensitive   = true
}
