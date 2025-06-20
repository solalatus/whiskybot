terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.50" }
  }
  required_version = ">= 1.7"
}

provider "aws" {
  region = var.aws_region       # read from variables.tf
}
