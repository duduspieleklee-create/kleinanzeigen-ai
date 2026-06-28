variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "redis_name" {
  description = "Name of the Redis cache instance (globally unique)"
  type        = string
}

variable "sku_name" {
  description = "Redis SKU — Basic (dev), Standard (staging), Premium (prod)"
  type        = string
  default     = "Basic"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku_name)
    error_message = "sku_name must be Basic, Standard, or Premium"
  }
}

variable "family" {
  description = "Redis family — C for Basic/Standard, P for Premium"
  type        = string
  default     = "C"
}

variable "capacity" {
  description = "Redis cache size (0=250MB, 1=1GB, 2=6GB, ...)"
  type        = number
  default     = 1
}
