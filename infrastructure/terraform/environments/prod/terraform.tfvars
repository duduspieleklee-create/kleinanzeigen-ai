resource_group_name = "kleinanzeigen-ai-prod-rg"
location            = "westeurope"

acr_name = "kleinanzeigenacrprod"

postgres_server_name    = "kleinanzeigen-db-prod"
postgres_admin_username = "kleinanzeigenadmin"
# postgres_admin_password is intentionally absent.
# Pass it at runtime via the TF_VAR_postgres_admin_password environment variable:
#   export TF_VAR_postgres_admin_password="your-password"
#   terraform apply

redis_name = "kleinanzeigen-redis-prod"

key_vault_name = "kleinanzeigen-kv-prod"
