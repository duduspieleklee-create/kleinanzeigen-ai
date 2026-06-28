resource_group_name = "kleinanzeigen-ai-staging-rg"
location            = "westeurope"

acr_name = "kleinanzeigenacrstaging"

aks_cluster_name = "kleinanzeigen-aks-staging"
node_count       = 3
vm_size          = "Standard_B2s"

postgres_server_name    = "kleinanzeigen-db-staging"
postgres_admin_username = "kleinanzeigenadmin"
postgres_admin_password = "ChangeThisPassword123!"

redis_name = "kleinanzeigen-redis-staging"

key_vault_name = "kleinanzeigen-kv-staging"
