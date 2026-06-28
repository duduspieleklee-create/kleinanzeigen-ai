variable "key_vault_name" {
  description = "Name of the Azure Key Vault"
  type        = string
}


variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "westeurope"
}

variable "acr_name" {
  description = "Name of the Azure Container Registry"
  type        = string
}

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

variable "postgres_server_name" {
  description = "Name of the PostgreSQL server"
  type        = string
}

variable "postgres_admin_username" {
  description = "PostgreSQL admin username"
  type        = string
}

variable "postgres_admin_password" {
  description = "PostgreSQL admin password"
  type        = string
  sensitive   = true
}

variable "redis_name" {
  description = "Name of the Redis cache"
  type        = string
}
