# Copy this file to terraform.tfvars for prod deployments.
# Never commit terraform.tfvars — it is gitignored.
# For postgres_admin_password, use the TF_VAR_ env var approach instead (see docs/terraform.md).

resource_group_name = "kleinanzeigen-ai-prod-rg"
location            = "westeurope"
acr_name            = "kleinanzeigenacrprod"
aks_cluster_name    = "kleinanzeigen-aks-prod"
node_count          = 3
vm_size             = "Standard_D2s_v3"
postgres_server_name    = "kleinanzeigen-db-prod"
postgres_admin_username = "kleinanzeigenadmin"
redis_name     = "kleinanzeigen-redis-prod"
key_vault_name = "kleinanzeigen-kv-prod"
