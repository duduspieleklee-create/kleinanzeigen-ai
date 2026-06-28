resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.cluster_name
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = var.cluster_name

  default_node_pool {
    name       = "default"
    node_count = var.node_count
    vm_size    = var.vm_size
  }

  identity {
    type = "SystemAssigned"
  }

  # Required for Azure Key Vault secret injection into pods
  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  # Required for pod-level managed identity (Workload Identity)
  workload_identity_enabled = true
  oidc_issuer_enabled       = true

  tags = {
    cluster = var.cluster_name
  }
}
