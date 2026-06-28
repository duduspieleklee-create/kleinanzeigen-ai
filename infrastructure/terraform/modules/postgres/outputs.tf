output "fqdn" {
  description = "Fully qualified domain name of the PostgreSQL server"
  value       = azurerm_postgresql_flexible_server.db.fqdn
}

output "database_name" {
  description = "Name of the application database"
  value       = azurerm_postgresql_flexible_server_database.kleinanzeigen.name
}

output "database_url" {
  description = "Full PostgreSQL connection string (sensitive) — use this as DATABASE_URL"
  value       = "postgresql://${var.admin_username}:${var.admin_password}@${azurerm_postgresql_flexible_server.db.fqdn}:5432/kleinanzeigen_ai"
  sensitive   = true
}
