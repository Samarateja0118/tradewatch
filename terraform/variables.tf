variable "region" {
  description = "AWS region for every resource in this configuration."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for all resources. Also the ECR repository name."
  type        = string
  default     = "tradewatch"

  validation {
    # Lambda, ECR and S3 all disagree about what characters they allow. This is
    # the intersection, checked once here rather than as four apply-time errors.
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.project))
    error_message = "project must be lowercase alphanumeric with hyphens, 2-31 chars, starting with a letter."
  }
}

variable "snapshot_bucket_name" {
  description = <<-EOT
    Globally unique name for the snapshot bucket. S3 bucket names share one
    global namespace, so this cannot be derived from `project` alone without
    colliding with someone else's bucket.
  EOT
  type        = string
}

variable "snapshot_key" {
  description = "Object key the API reads the SQLite snapshot from."
  type        = string
  default     = "snapshot.db"
}

variable "image_tag" {
  description = <<-EOT
    ECR image tag to deploy. Pin to a digest or an immutable tag in anything
    real: `latest` makes an apply non-reproducible, because the same config
    yields a different running image depending on when it ran.
  EOT
  type        = string
  default     = "latest"
}

variable "log_retention_days" {
  description = <<-EOT
    CloudWatch retention. The AWS default is "never expire", which is a bill
    that grows forever and is never noticed. 14 days is long enough to debug a
    deploy and short enough to cost nothing.
  EOT
  type        = number
  default     = 14

  validation {
    condition = contains(
      [1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653],
      var.log_retention_days
    )
    error_message = "CloudWatch accepts only a fixed set of retention values; 0 (never expire) is deliberately not one of them here."
  }
}

variable "allowed_origins" {
  description = "Origins the API returns CORS headers for. The deployed frontend's origin belongs here."
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "memory_mb" {
  description = "Lambda memory. CPU scales with it, so this is also the speed dial."
  type        = number
  default     = 512
}

variable "timeout_seconds" {
  description = "Lambda timeout. Requests are one SQLite read; the cold-start S3 fetch is the slow path."
  type        = number
  default     = 15
}
