# ---------------------------------------------------------------------------
# S3: the SQLite snapshot the API serves.
#
# WHY THIS EXISTS AT ALL. The Dockerfile used to bake data/snapshot.db into the
# image, and that was the right call for a single-container host: nothing writes
# to the database at runtime, so an ephemeral filesystem cost nothing. What it
# did cost was a rebuild and a redeploy every time the pipeline produced fresher
# briefings — DEPLOYING.md called that out and deferred it. Putting the snapshot
# in S3 decouples the two: the pipeline uploads, the API picks it up on its next
# cold start, and no image is rebuilt. The least-privilege IAM policy is a
# consequence of that decision, not the reason for it.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "snapshot" {
  bucket = var.snapshot_bucket_name
}

resource "aws_s3_bucket_versioning" "snapshot" {
  bucket = aws_s3_bucket.snapshot.id

  versioning_configuration {
    # The pipeline overwrites one key in place. Without versioning a bad run
    # silently replaces good data with no way back; with it, rollback is
    # selecting an earlier version.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "snapshot" {
  bucket = aws_s3_bucket.snapshot.id

  # All four, explicitly. These default to true on new buckets now, but writing
  # them down means the guarantee survives someone loosening it in the console —
  # the next plan puts it back.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "snapshot" {
  bucket = aws_s3_bucket.snapshot.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ---------------------------------------------------------------------------
# ECR: the API container image.
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "api" {
  name = var.project

  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  # Left false on purpose: `terraform destroy` should refuse to delete a
  # repository that still holds images rather than quietly discarding them.
  force_delete = false
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  # Same argument as the log retention: storage that nothing ever deletes is a
  # bill nobody reads. Untagged layers accumulate on every push.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the 10 most recent tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      },
    ]
  })
}
