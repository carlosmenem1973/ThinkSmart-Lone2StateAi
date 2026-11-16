terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
  backend "s3" {}
}
provider "aws" {
  region = var.aws_region
  default_tags { tags = { Project = "ThinkSmart-Lone2StateAi", Environment = "prod", ManagedBy = "OpenTofu" } }
}

provider "aws" {
  alias = "use1"
  region = "us-east-1"
}
