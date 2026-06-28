# Resource Group
resource_group_name = "kleinanzeigen-ai-dev-rg"
location            = "westeurope"

# Azure Container Registry
acr_name = "kleinanzeigenacrdev"

# AKS Cluster
aks_cluster_name = "kleinanzeigen-aks-dev"
node_count       = 2
vm_size          = "Standard_B2s"

# PostgreSQL
postgres_server_name    = "kleinanzeigen-db-dev"
postgres_admin_username = "kleinanzeigenadmin"
# postgres_admin_password is intentionally absent.
# Pass it at runtime via the TF_VAR_postgres_admin_password environment variable:
#   export TF_VAR_postgres_admin_password="your-password"
#   terraform apply

# Redis
redis_name = "kleinanzeigen-redis-dev"

# Key Vault
key_vault_name = "kleinanzeigen-kv-dev"
