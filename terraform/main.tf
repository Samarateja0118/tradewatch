# Providers and remote state.
#
# The backend is deliberately a PARTIAL configuration: a backend block cannot
# interpolate variables or locals — it is read before Terraform evaluates
# anything — so the bucket name, which has to be globally unique and therefore
# differs per person, is supplied at init time instead:
#
#   terraform init -backend-config=backend.hcl
#
# See backend.hcl.example. The state bucket and lock table must already exist
# before this runs; that is what bootstrap/ is for.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    key            = "tradewatch/terraform.tfstate"
    dynamodb_table = "tradewatch-tf-locks"
    encrypt        = true
    # bucket and region come from -backend-config.
    #
    # DynamoDB locking is used here because it is the mechanism worth being able
    # to explain: without a lock, two people running apply at once interleave
    # writes and corrupt state. Recent provider versions also support S3-native
    # locking (`use_lockfile = true`), which removes the table entirely; that is
    # the migration to make once the table is no longer the interesting part.
  }
}

provider "aws" {
  region = var.region

  # Every resource gets these. Untagged infrastructure is unattributable
  # infrastructure — you cannot answer "what is this and who pays for it"
  # six months later from the console alone.
  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Repo      = "github.com/Samarateja0118/tradewatch"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  function_name = "${var.project}-api"
  log_group     = "/aws/lambda/${var.project}-api"
}
