resource "aws_cloudwatch_metric_alarm" "c2_quarantine_errors" {
  alarm_name = (
    "${var.project_name}-${var.environment}-c2-quarantine-errors"
  )

  alarm_description = (
    "C2 quarantine Lambda reported one or more invocation errors."
  )

  namespace   = "AWS/Lambda"
  metric_name = "Errors"

  statistic = "Sum"
  period    = 60

  evaluation_periods  = 1
  datapoints_to_alarm = 1

  threshold = 1

  comparison_operator = (
    "GreaterThanOrEqualToThreshold"
  )

  treat_missing_data = "notBreaching"

  dimensions = {
    FunctionName = (
      aws_lambda_function.c2_quarantine.function_name
    )
  }
}

resource "aws_cloudwatch_metric_alarm" "c2_fallback_executions_failed" {
  alarm_name = (
    "${var.project_name}-${var.environment}-c2-fallback-executions-failed"
  )

  alarm_description = (
    "C2 fallback Step Functions executions entered a failed terminal state."
  )

  namespace   = "AWS/States"
  metric_name = "ExecutionsFailed"

  statistic = "Sum"
  period    = 60

  evaluation_periods  = 1
  datapoints_to_alarm = 1

  threshold = 1

  comparison_operator = (
    "GreaterThanOrEqualToThreshold"
  )

  treat_missing_data = "notBreaching"

  dimensions = {
    StateMachineArn = (
      aws_sfn_state_machine.c2_fallback.arn
    )
  }
}

resource "aws_cloudwatch_metric_alarm" "c2_fallback_executions_timed_out" {
  alarm_name = (
    "${var.project_name}-${var.environment}-c2-fallback-executions-timed-out"
  )

  alarm_description = (
    "C2 fallback Step Functions executions timed out."
  )

  namespace   = "AWS/States"
  metric_name = "ExecutionsTimedOut"

  statistic = "Sum"
  period    = 60

  evaluation_periods  = 1
  datapoints_to_alarm = 1

  threshold = 1

  comparison_operator = (
    "GreaterThanOrEqualToThreshold"
  )

  treat_missing_data = "notBreaching"

  dimensions = {
    StateMachineArn = (
      aws_sfn_state_machine.c2_fallback.arn
    )
  }
}
