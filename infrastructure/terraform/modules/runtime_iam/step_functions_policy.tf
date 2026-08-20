data "aws_iam_policy_document" "step_functions_runtime" {
  statement {
    sid    = "InvokeC2QuarantineLambda"
    effect = "Allow"

    actions = [
      "lambda:InvokeFunction"
    ]

    resources = [
      "arn:${local.partition}:lambda:${var.aws_region}:${var.aws_account_id}:function:${local.name_prefix}-c2-quarantine"
    ]
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
