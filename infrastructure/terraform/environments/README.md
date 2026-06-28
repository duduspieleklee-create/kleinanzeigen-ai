Content:
# Terraform Environment Configurations

This folder contains environment-specific variable files (`terraform.tfvars`) for deploying the **kleinanzeigen-ai** infrastructure.

## Folder Structure
environments/
├── dev/
│   └── terraform.tfvars
├── staging/
│   └── terraform.tfvars
└── prod/
└── terraform.tfvars
## How to Use

When running Terraform commands, specify the environment file using the `-var-file` flag:

### Development
```bash
terraform plan  -var-file="environments/dev/terraform.tfvars"
terraform apply -var-file="environments/dev/terraform.tfvars"
Staging
terraform plan  -var-file="environments/staging/terraform.tfvars"
terraform apply -var-file="environments/staging/terraform.tfvars"
Production
terraform plan  -var-file="environments/prod/terraform.tfvars"
terraform apply -var-file="environments/prod/terraform.tfvars"
Important Notes
Never commit real secrets (especially postgres_admin_password) to Git.
Use Azure Key Vault or environment variables for sensitive values in production.
Always double-check which environment you are deploying to before running terraform apply.
It is recommended to use separate resource groups and naming conventions per environment.
Recommended Workflow
Make changes in your Terraform code.
Run terraform plan with the correct environment file.
Review the planned changes carefully.
Run terraform apply only when you're confident.
Backend Configuration
Make sure you have initialized Terraform with the correct backend before running plan/apply:
terraform init -backend-config=backend-config.dev.conf
---

This README helps anyone (including future team members) understand how to work with the different environments.

Would you like me to continue with anything else (e.g., improving the Celery task further, final review, or moving to Octopus Deploy setup)?
