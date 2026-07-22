data "aws_iam_policy_document" "step_functions_runtime" {
  statement {
    sid    = "RunGlueJobsSynchronously"
    effect = "Allow"

    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun"
    ]

    resources = ["*"]
  }

  statement {
    sid    = "InvokeProjectLambdaFunctions"
    effect = "Allow"

    actions = [
      "lambda:InvokeFunction"
    ]

    resources = local.project_lambda_function_arns
  }

  statement {
    sid    = "WriteStepFunctionsExecutionLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups"
    ]

    resources = ["*"]
  }
}
