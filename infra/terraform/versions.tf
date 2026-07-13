terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Bootstrapped once via AWS CLI before the first `terraform init` — a
  # backend can't provision its own storage. See README.md's "Bootstrap"
  # section for the exact commands (S3 bucket with versioning + AES256
  # encryption + public access block, plus a DynamoDB lock table).
  backend "s3" {
    bucket         = "ocen-platform-tfstate-572914130294"
    key            = "rke2-foundation/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "ocen-platform-tfstate-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "ocen-platform"
      Component   = "rke2-foundation"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
