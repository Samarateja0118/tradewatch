output "function_url" {
  description = "Public base URL of the API. Health check: <url>api/health"
  value       = aws_lambda_function_url.api.function_url
}

output "snapshot_bucket" {
  description = "Upload a refreshed snapshot here to update the API without redeploying."
  value       = aws_s3_bucket.snapshot.bucket
}

output "snapshot_uri" {
  description = "Full S3 URI the Lambda reads at cold start."
  value       = "s3://${aws_s3_bucket.snapshot.bucket}/${var.snapshot_key}"
}

output "ecr_repository_url" {
  description = "docker tag / docker push target."
  value       = aws_ecr_repository.api.repository_url
}

output "log_group" {
  description = "CloudWatch log group, with retention set explicitly."
  value       = aws_cloudwatch_log_group.api.name
}

output "lambda_role_arn" {
  description = "Execution role. Scoped to one S3 object and one log group."
  value       = aws_iam_role.lambda.arn
}
