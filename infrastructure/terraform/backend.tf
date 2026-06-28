terraform {
  # Backend config is supplied per environment via:
  #   terraform init -backend-config=backend-config.<env>.conf
  # See infrastructure/terraform/backend-config.dev.conf for the dev example.
  backend "azurerm" {}
}
