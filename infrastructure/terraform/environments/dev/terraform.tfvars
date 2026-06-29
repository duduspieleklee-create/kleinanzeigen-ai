# ==========================================
# Development Environment Configuration
# ==========================================

resource_group_name = "kleinanzeigen-ai-dev-rg"
location            = "westeurope"
environment         = "dev"

# Azure Container Registry
acr_name = "kleinanzeigenacrdev"

# PostgreSQL Database
postgres_server_name    = "kleinanzeigen-db-dev"
postgres_admin_username = "kleinanzeigenadmin"
postgres_admin_password = "ChangeThisToAStrongPassword123!"

# Azure Cache for Redis
redis_name = "kleinanzeigen-redis-dev"

# Azure Key Vault
key_vault_name = "kleinanzeigen-kv-dev"
