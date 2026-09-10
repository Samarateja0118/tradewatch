# The execution role. The whole point of this file is that the Lambda can read
# exactly one prefix of one bucket and write to exactly one log group.

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "lambda" {
  # Read the snapshot. `s3:GetObject` on one object ARN — not `s3:*`, not `*`.
  # Note there is no `s3:ListBucket`: the key is known from configuration, so
  # the function never needs to enumerate the bucket to find it.
  statement {
    sid       = "ReadSnapshotObject"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.snapshot.arn}/${var.snapshot_key}"]
  }

  # Write logs — to this function's log group only, and *not* CreateLogGroup.
  # Terraform owns the group (see observability.tf), so granting the function
  # permission to create one would only let it create a second, unmanaged group
  # with no retention policy if the name ever drifted.
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# NOT USED, deliberately: AWSLambdaBasicExecutionRole is the managed policy most
# tutorials attach here. It grants logs:* across every log group in the account.
# The inline statement above is the same capability scoped to one group.
