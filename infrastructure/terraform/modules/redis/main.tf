resource "azurerm_redis_cache" "redis" {
  name                = var.redis_name
  resource_group_name = var.resource_group_name
  location            = var.location
  capacity            = var.capacity
  family              = var.family
  sku_name            = var.sku_name

  # Enable TLS-only access (port 6380) — required for Azure Redis
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"

  redis_configuration {}
}
