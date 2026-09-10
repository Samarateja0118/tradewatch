resource "aws_cloudwatch_log_group" "api" {
  # Lambda writes to /aws/lambda/<function-name> whether or not the group
  # exists. If it does not, Lambda creates it — with retention set to "never
  # expire", and outside Terraform's state. Declaring it here means the name is
  # claimed before the function can auto-create it, which is why compute.tf has
  # an explicit depends_on.
  name              = local.log_group
  retention_in_days = var.log_retention_days
}
