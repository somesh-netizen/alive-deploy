# One-click deploy of customer_support_ops to Azure Container Apps.
terraform { required_providers { azurerm = { source = "hashicorp/azurerm" } } }
provider "azurerm" { features {} }
variable "resource_group" {}
variable "location" { default = "eastus" }
variable "image"    { description = "Pushed image, e.g. <acr>.azurecr.io/customer_support_ops:latest" }
variable "openai_api_key" { default = "", sensitive = true }

resource "azurerm_container_app_environment" "env" {
  name                = "alive-customer_support_ops-env"
  resource_group_name = var.resource_group
  location            = var.location
}
resource "azurerm_container_app" "customer_support_ops" {
  name                         = "alive-customer_support_ops"
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = var.resource_group
  revision_mode                = "Single"
  template {
    container {
      name   = "app"
      image  = var.image
      cpu    = 1.0
      memory = "2Gi"
      env { name = "OPENAI_API_KEY", secret_name = "openai-api-key" }
    }
  }
  ingress { external_enabled = true, target_port = 8080, traffic_weight { percentage = 100, latest_revision = true } }
  secret { name = "openai-api-key", value = var.openai_api_key }
}
