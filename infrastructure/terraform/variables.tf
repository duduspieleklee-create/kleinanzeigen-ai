# ==========================================
# General Configuration
# ==========================================
variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
}

variable "location" {
  description = "Azure region to deploy resources into"
  type        = string
  default     = "westeurope"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ==========================================
# Azure Container Registry (ACR)
# ==========================================
variable "acr_name" {
  description = "Name of the Azure Container Registry"
  type        = string
}

# ==========================================
# Azure Kubernetes Service (AKS)
# ==========================================
variable "aks_cluster_name" {
  description = "Name of the AKS cluster"
  type        = string
}

variable "node_count" {
  description = "Number of nodes in the default node pool"
  type        = number
  default     = 2
}

variable "vm_size" {
  description = "VM size for AKS nodes"
  type        = string
  default     = "Standard_B2s"
}

# ==========================================
# Azure Database for PostgreSQL
# ==========================================
variable "postgres_server_name" {
  description = "Name of the PostgreSQL Flexible Server"
  type        = string
}

variable "postgres_admin_username" {
  description = "PostgreSQL administrator username"
  type        = string
}

variable "postgres_admin_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

# ==========================================
# Azure Cache for Redis
# ==========================================
variable "redis_name" {
  description = "Name of the Redis Cache instance"
  type        = string
}

# ==========================================
# Azure Key Vault
# ==========================================
variable "key_vault_name" {
  description = "Name of the Azure Key Vault"
  type        = string
}
