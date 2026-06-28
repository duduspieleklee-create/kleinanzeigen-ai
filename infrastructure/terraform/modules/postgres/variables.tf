variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "server_name" {
  description = "Name of the PostgreSQL Flexible Server (globally unique)"
  type        = string
}

variable "admin_username" {
  description = "PostgreSQL administrator login"
  type        = string
}

variable "admin_password" {
  description = "PostgreSQL administrator password (sensitive)"
  type        = string
  sensitive   = true
}

variable "sku_name" {
  description = "PostgreSQL SKU — e.g. B_Standard_B1ms (dev) or GP_Standard_D2s_v3 (prod)"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "storage_mb" {
  description = "Storage size in MB"
  type        = number
  default     = 32768
}
