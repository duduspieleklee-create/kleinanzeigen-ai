data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    environment = var.environment
    project     = "kleinanzeigen-ai"
  }
}

module "acr" {
  source              = "./modules/acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  acr_name            = var.acr_name
}

module "aks" {
  source              = "./modules/aks"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  cluster_name        = var.aks_cluster_name
  node_count          = var.node_count
  vm_size             = var.vm_size
}

module "postgres" {
  source              = "./modules/postgres"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  server_name         = var.postgres_server_name
  admin_username      = var.postgres_admin_username
  admin_password      = var.postgres_admin_password
}

module "redis" {
  source              = "./modules/redis"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  redis_name          = var.redis_name
}

resource "azurerm_key_vault" "main" {
  name                        = var.key_vault_name
  location                    = azurerm_resource_group.main.location
  resource_group_name         = azurerm_resource_group.main.name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 7
  purge_protection_enabled    = true

  tags = {
    environment = var.environment
  }
}
