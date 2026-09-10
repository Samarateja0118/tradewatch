# Bootstrap: the state bucket and lock table.
#
# THE CHICKEN AND EGG. The root configuration keeps its state in S3 with a
# DynamoDB lock. Neither exists yet on a fresh account, and Terraform cannot
# initialise a backend that points at a bucket it has not created. There are
# three ways out and it is worth knowing why this is the one:
#
#   1. Create them by hand in the console. Works, but the two resources every
#      other resource depends on are then the only two nobody can review.
#   2. Create them here with LOCAL state, and leave that state local. Chosen.
#      The state file for this config describes two resources that change
#      approximately never, and losing it costs an import, not an outage.
#   3. Create them here, then migrate this config's own state into the bucket it
#      just created. Elegant, and one `terraform destroy` away from a config
#      whose state lives inside a bucket it is trying to delete.
#
# Run once:
#   cd terraform/bootstrap && terraform init && terraform apply
# Then take the outputs into ../backend.hcl.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Local state, on purpose. See above.
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform-bootstrap"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "tradewatch"
}

variable "state_bucket_name" {
  description = "Globally unique name for the state bucket."
  type        = string
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  # State is the one thing whose accidental deletion is unrecoverable: without
  # it Terraform no longer knows that any of the real infrastructure is his.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    # Not optional for a state bucket. Every apply overwrites the same key, so
    # versioning is the only way back from a corrupted or truncated write.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_dynamodb_table" "locks" {
  name = "${var.project}-tf-locks"

  # A row exists only while an apply is running, so provisioned capacity would
  # be paying for an idle table. On-demand costs nothing at rest.
  billing_mode = "PAY_PER_REQUEST"

  # The attribute name is not a choice — the S3 backend writes a lock item
  # keyed on exactly "LockID".
  hash_key = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "backend_hcl" {
  description = "Paste into ../backend.hcl"
  value       = <<-EOT
    bucket = "${aws_s3_bucket.state.bucket}"
    region = "${var.region}"
  EOT
}
