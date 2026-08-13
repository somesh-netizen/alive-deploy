# One-click deploy of customer_support_ops to AWS (ECS Fargate + App Runner-style).
# Skeleton — fill vars, then: terraform init && terraform apply
terraform { required_providers { aws = { source = "hashicorp/aws" } } }
provider "aws" { region = var.region }
variable "region"  { default = "us-east-1" }
variable "image"   { description = "Pushed image, e.g. <acct>.dkr.ecr.<region>.amazonaws.com/customer_support_ops:latest" }
variable "openai_api_key" { default = "", sensitive = true }

resource "aws_apprunner_service" "customer_support_ops" {
  service_name = "alive-customer_support_ops"
  source_configuration {
    image_repository {
      image_identifier      = var.image
      image_repository_type = "ECR"
      image_configuration {
        port = "8080"
        runtime_environment_variables = { OPENAI_API_KEY = var.openai_api_key }
      }
    }
  }
  instance_configuration { cpu = "1024", memory = "2048" }
}
output "url" { value = aws_apprunner_service.customer_support_ops.service_url }
