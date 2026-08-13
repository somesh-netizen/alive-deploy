# One-click deploy of customer_support_ops to GCP Cloud Run.
terraform { required_providers { google = { source = "hashicorp/google" } } }
provider "google" { project = var.project, region = var.region }
variable "project" {}
variable "region"  { default = "us-central1" }
variable "image"   { description = "Pushed image, e.g. <region>-docker.pkg.dev/<project>/customer_support_ops/app:latest" }
variable "openai_api_key" { default = "", sensitive = true }

resource "google_cloud_run_v2_service" "customer_support_ops" {
  name     = "alive-customer_support_ops"
  location = var.region
  template {
    containers {
      image = var.image
      ports { container_port = 8080 }
      env { name = "OPENAI_API_KEY", value = var.openai_api_key }
    }
  }
}
output "url" { value = google_cloud_run_v2_service.customer_support_ops.uri }
