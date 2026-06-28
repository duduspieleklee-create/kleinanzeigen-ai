variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "project" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "kleinanzeigen-ai"
}
