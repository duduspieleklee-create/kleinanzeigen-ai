resource_group_name = "kleinanzeigen-ai-prod-rg"
location            = "westeurope"

acr_name = "kleinanzeigenacrprod"

aks_cluster_name = "kleinanzeigen-aks-prod"
node_count       = 3
vm_size          = "Standard_D2s_v3"

postgres_server_name    = "kleinanzeigen-db-prod"
postgres_admin_username = "kleinanzeigenadmin"
postgres_admin_password = "VeryStrongProdPassword123!"

redis_name = "kleinanzeigen-redis-prod"

key_vault_name = "kleinanzeigen-kv-prod"
