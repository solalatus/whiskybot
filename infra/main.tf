# main.tf
terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.50" }
  }
}

provider "aws" {
  region = "eu-central-1"   # or omit and rely on the CLI profile
}
