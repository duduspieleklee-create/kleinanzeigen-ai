output "cluster_name" {
  description = "Name of the AKS cluster"
  value       = azurerm_kubernetes_cluster.aks.name
}

output "kube_config" {
  description = "Raw kubeconfig for the cluster (sensitive)"
  value       = azurerm_kubernetes_cluster.aks.kube_config_raw
  sensitive   = true
}

output "identity_principal_id" {
  description = "Principal ID of the cluster system-assigned managed identity"
  value       = azurerm_kubernetes_cluster.aks.identity[0].principal_id
}

output "oidc_issuer_url" {
  description = "OIDC issuer URL (needed to configure Workload Identity federation)"
  value       = azurerm_kubernetes_cluster.aks.oidc_issuer_url
}
