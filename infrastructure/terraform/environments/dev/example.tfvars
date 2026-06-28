# Copy this file to terraform.tfvars for local development.
# Never commit terraform.tfvars — it is gitignored.
# For postgres_admin_password, use the TF_VAR_ env var approach instead (see docs/terraform.md).

resource_group_name = "kleinanzeigen-ai-dev-rg"
location            = "westeurope"
acr_name            = "kleinanzeigenacrdev"
aks_cluster_name    = "kleinanzeigen-aks-dev"
node_count          = 2
vm_size             = "Standard_B2s"
postgres_server_name    = "kleinanzeigen-db-dev"
postgres_admin_username = "kleinanzeigenadmin"
redis_name     = "kleinanzeigen-redis-dev"
key_vault_name = "kleinanzeigen-kv-dev"
