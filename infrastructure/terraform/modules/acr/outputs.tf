output "login_server" {
  description = "Login server URL for the container registry"
  value       = azurerm_container_registry.acr.login_server
}

output "admin_username" {
  description = "Admin username for the container registry"
  value       = azurerm_container_registry.acr.admin_username
}

output "admin_password" {
  description = "Admin password for the container registry (sensitive)"
  value       = azurerm_container_registry.acr.admin_password
  sensitive   = true
}
