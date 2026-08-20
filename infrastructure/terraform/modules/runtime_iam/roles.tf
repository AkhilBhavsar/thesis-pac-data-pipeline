resource "aws_iam_role" "glue_runtime" {
  name               = "AWSGlueServiceRole-${local.name_prefix}-runtime"
  description        = "Execution role for thesis Glue ETL jobs."
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json

  max_session_duration = 3600
}

resource "aws_iam_policy" "glue_runtime" {
  name        = "${local.name_prefix}-glue-runtime"
  description = "Scoped S3, Glue Catalog and logging permissions for thesis Glue jobs."
  policy      = data.aws_iam_policy_document.glue_runtime.json
}

resource "aws_iam_role_policy_attachment" "glue_runtime" {
  role       = aws_iam_role.glue_runtime.name
  policy_arn = aws_iam_policy.glue_runtime.arn
}

resource "aws_iam_role" "lambda_runtime" {
  name               = "${local.name_prefix}-lambda-runtime"
  description        = "Execution role for thesis validation and remediation Lambda functions."
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  max_session_duration = 3600
}

resource "aws_iam_policy" "lambda_runtime" {
  name        = "${local.name_prefix}-lambda-runtime"
  description = "Scoped data-lake, Glue and Athena permissions for thesis Lambda functions."
  policy      = data.aws_iam_policy_document.lambda_runtime.json
}

resource "aws_iam_role_policy_attachment" "lambda_runtime" {
  role       = aws_iam_role.lambda_runtime.name
  policy_arn = aws_iam_policy.lambda_runtime.arn
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logging" {
  role = aws_iam_role.lambda_runtime.name

  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role" "c2_quarantine_runtime" {
  name = "${local.name_prefix}-c2-quarantine-runtime"

  description = (
    "Least-privilege Lambda execution role for C2 quarantine containment."
  )

  assume_role_policy = (
    data.aws_iam_policy_document.lambda_assume_role.json
  )

  max_session_duration = 3600
}

resource "aws_iam_policy" "c2_quarantine_runtime" {
  name = "${local.name_prefix}-c2-quarantine-runtime"

  description = (
    "Least-privilege C2 experiment, quarantine, Athena and Glue permissions."
  )

  policy = (
    data.aws_iam_policy_document.c2_quarantine_runtime.json
  )
}

resource "aws_iam_role_policy_attachment" "c2_quarantine_runtime" {
  role = (
    aws_iam_role.c2_quarantine_runtime.name
  )

  policy_arn = (
    aws_iam_policy.c2_quarantine_runtime.arn
  )
}

resource "aws_iam_role_policy_attachment" "c2_quarantine_basic_logging" {
  role = (
    aws_iam_role.c2_quarantine_runtime.name
  )

  policy_arn = (
    "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  )
}

resource "aws_iam_role" "step_functions_runtime" {
  name               = "${local.name_prefix}-step-functions-runtime"
  description        = "Execution role for thesis pipeline Step Functions workflows."
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume_role.json

  max_session_duration = 3600
}

resource "aws_iam_policy" "step_functions_runtime" {
  name        = "${local.name_prefix}-step-functions-runtime"
  description = "Scoped Glue, Lambda and logging permissions for thesis Step Functions."
  policy      = data.aws_iam_policy_document.step_functions_runtime.json
}

resource "aws_iam_role_policy_attachment" "step_functions_runtime" {
  role       = aws_iam_role.step_functions_runtime.name
  policy_arn = aws_iam_policy.step_functions_runtime.arn
}
