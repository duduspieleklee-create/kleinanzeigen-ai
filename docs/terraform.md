# Terraform Runbook

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) logged in:
  ```bash
  az login
  az account set --subscription <your-subscription-id>
  ```

## Sensitive variables

`postgres_admin_password` is marked `sensitive = true` in Terraform and is **never stored in `.tfvars`**.
Pass it as an environment variable before running any Terraform command:

```bash
export TF_VAR_postgres_admin_password="your-strong-password-here"
```

For production, store this value in Azure Key Vault or your CI secret store (see CI section below).

## First-time setup (per environment)

```bash
cd infrastructure/terraform/environments/dev

# Initialise with the remote Azure backend
terraform init -backend-config=../../backend-config.dev.conf

# Preview changes
terraform plan -var-file=terraform.tfvars

# Apply
terraform apply -var-file=terraform.tfvars
```

## CI / GitHub Actions

Add the following repository secrets in GitHub → Settings → Secrets and variables → Actions:

| Secret name | Value |
|---|---|
| `TF_VAR_POSTGRES_ADMIN_PASSWORD_DEV` | Dev DB password |
| `TF_VAR_POSTGRES_ADMIN_PASSWORD_PROD` | Prod DB password |
| `AZURE_CLIENT_ID` | Service principal / managed identity client ID |
| `AZURE_CLIENT_SECRET` | Service principal secret |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_TENANT_ID` | `f196df42-b27f-416b-b16f-d6f83a94cd0f` |

In the workflow step:

```yaml
- name: Terraform Apply
  env:
    TF_VAR_postgres_admin_password: ${{ secrets.TF_VAR_POSTGRES_ADMIN_PASSWORD_DEV }}
    ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
    ARM_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
    ARM_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    ARM_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  run: terraform apply -auto-approve -var-file=terraform.tfvars
  working-directory: infrastructure/terraform/environments/dev
```

## Outputs

After `terraform apply`, retrieve connection strings with:

```bash
terraform output -raw postgres_connection_string
terraform output -raw redis_connection_string
```

Use these values when populating Azure Key Vault secrets (`DatabaseConnectionString`, `RedisConnectionString`).
