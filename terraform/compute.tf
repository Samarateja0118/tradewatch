resource "aws_lambda_function" "api" {
  function_name = local.function_name
  role          = aws_iam_role.lambda.arn

  # A container image rather than a zip. FastAPI plus its dependencies is
  # awkward in a 250 MB unzipped layer budget, and the image is the same
  # artifact shape the project already builds for every other host.
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"

  memory_size = var.memory_mb
  timeout     = var.timeout_seconds

  environment {
    variables = {
      TRADEWATCH_SNAPSHOT_BUCKET = aws_s3_bucket.snapshot.bucket
      TRADEWATCH_SNAPSHOT_KEY    = var.snapshot_key
      TRADEWATCH_ALLOWED_ORIGINS = join(",", var.allowed_origins)
      # TRADEWATCH_DB is deliberately absent. /tmp is the only writable path in
      # a Lambda, so the handler sets it; making it configurable would let
      # someone point it somewhere read-only and fail at startup.
    }
  }

  # Without this, a first invocation can create /aws/lambda/<name> itself,
  # unmanaged and with unbounded retention, before Terraform gets there.
  depends_on = [aws_cloudwatch_log_group.api]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  # NONE is a decision, not an oversight. This serves a read-only dashboard of
  # published government documents: no secrets, no writes, no user data, and the
  # IAM role above cannot reach anything except one S3 object. IAM auth would
  # mean the browser needs SigV4 credentials to read a public dashboard.
  #
  # CORS is deliberately NOT configured here. FastAPI's CORSMiddleware already
  # handles it from TRADEWATCH_ALLOWED_ORIGINS, and configuring it in both
  # places emits duplicate Access-Control-Allow-Origin headers, which browsers
  # reject. One source of truth, and it is the one that has tests.
}
