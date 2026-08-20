locals {
  c2_fallback_state_machine_name = (
    "${var.project_name}-${var.environment}-c2-fallback"
  )
}

resource "aws_cloudwatch_log_group" "c2_fallback" {
  name = (
    "/aws/vendedlogs/states/${local.c2_fallback_state_machine_name}"
  )

  retention_in_days = 14
}

resource "aws_sfn_state_machine" "c2_fallback" {
  name = local.c2_fallback_state_machine_name

  role_arn = (
    module.runtime_iam.role_arns["step_functions"]
  )

  type = "STANDARD"

  definition = jsonencode({
    Comment = (
      "C2 bounded post-verification fallback orchestration."
    )

    StartAt        = "ValidateC2Condition"
    TimeoutSeconds = 300

    States = {
      ValidateC2Condition = {
        Type = "Choice"

        Choices = [
          {
            Variable     = "$.condition"
            StringEquals = "C2"
            Next         = "ValidateScenarioFallback"
          }
        ]

        Default = "InvalidCondition"
      }

      ValidateScenarioFallback = {
        Type = "Choice"

        Choices = [
          {
            And = [
              {
                Variable     = "$.scenario_id"
                StringEquals = "pii_exposure"
              },
              {
                Variable     = "$.fallback_action"
                StringEquals = "quarantine"
              }
            ]

            Next = "InvokeQuarantine"
          },
          {
            And = [
              {
                Variable     = "$.scenario_id"
                StringEquals = "freshness_breach"
              },
              {
                Variable     = "$.fallback_action"
                StringEquals = "quarantine"
              }
            ]

            Next = "InvokeQuarantine"
          },
          {
            And = [
              {
                Variable     = "$.scenario_id"
                StringEquals = "quality_regression"
              },
              {
                Variable     = "$.fallback_action"
                StringEquals = "quarantine"
              }
            ]

            Next = "InvokeQuarantine"
          },
          {
            And = [
              {
                Variable     = "$.scenario_id"
                StringEquals = "schema_break"
              },
              {
                Variable     = "$.fallback_action"
                StringEquals = "manual_review"
              }
            ]

            Next = "ManualReview"
          },
          {
            And = [
              {
                Variable     = "$.scenario_id"
                StringEquals = "policy_false_positive"
              },
              {
                Variable     = "$.fallback_action"
                StringEquals = "stop_promotion"
              }
            ]

            Next = "StopPromotion"
          }
        ]

        Default = "InvalidScenarioFallback"
      }

      InvokeQuarantine = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"

        Parameters = {
          FunctionName = (
            aws_lambda_function.c2_quarantine.arn
          )

          Payload = {
            "condition.$" = "$.condition"
            "run_id.$"    = "$.run_key"

            "scenario_id.$" = (
              "$.scenario_id"
            )

            "source_bucket.$" = (
              "$.quarantine_request.source_bucket"
            )

            "source_key.$" = (
              "$.quarantine_request.source_key"
            )

            "source_dataset.$" = (
              "$.quarantine_request.source_dataset"
            )

            "source_relation.$" = (
              "$.quarantine_request.source_relation"
            )

            "policy_category.$" = (
              "$.quarantine_request.policy_category"
            )

            "policy_id.$" = (
              "$.quarantine_request.policy_id"
            )

            "violation_code.$" = (
              "$.quarantine_request.violation_code"
            )

            "violation_details.$" = (
              "$.quarantine_request.violation_details"
            )

            "data_classification.$" = (
              "$.quarantine_request.data_classification"
            )

            "detected_at.$" = (
              "$.quarantine_request.detected_at"
            )

            "retry_count.$" = (
              "$.quarantine_request.retry_count"
            )

            "max_retries.$" = (
              "$.quarantine_request.max_retries"
            )

            "evidence_uri.$" = (
              "$.quarantine_request.evidence_uri"
            )
          }
        }

        ResultPath = "$.quarantine_execution"

        Catch = [
          {
            ErrorEquals = [
              "States.ALL"
            ]

            ResultPath = "$.fallback_error"
            Next       = "QuarantineFailed"
          }
        ]

        Next = "Quarantined"
      }

      Quarantined = {
        Type = "Pass"

        Parameters = {
          "condition.$"       = "$.condition"
          "scenario_id.$"     = "$.scenario_id"
          "run_key.$"         = "$.run_key"
          "fallback_action.$" = "$.fallback_action"

          terminal_state    = "QUARANTINED"
          promotion_blocked = true

          "quarantine_result.$" = (
            "$.quarantine_execution.Payload"
          )
        }

        End = true
      }

      ManualReview = {
        Type = "Pass"

        Parameters = {
          "condition.$"       = "$.condition"
          "scenario_id.$"     = "$.scenario_id"
          "run_key.$"         = "$.run_key"
          "fallback_action.$" = "$.fallback_action"

          terminal_state    = "MANUAL_REVIEW"
          promotion_blocked = true
        }

        End = true
      }

      StopPromotion = {
        Type = "Pass"

        Parameters = {
          "condition.$"       = "$.condition"
          "scenario_id.$"     = "$.scenario_id"
          "run_key.$"         = "$.run_key"
          "fallback_action.$" = "$.fallback_action"

          terminal_state    = "FAILED_SAFE"
          promotion_blocked = true
        }

        End = true
      }

      InvalidCondition = {
        Type  = "Fail"
        Error = "C2InvalidCondition"

        Cause = (
          "Fallback state machine accepts only condition C2."
        )
      }

      InvalidScenarioFallback = {
        Type  = "Fail"
        Error = "C2InvalidScenarioFallback"

        Cause = (
          "Scenario and fallback action do not match the bounded C2 catalog."
        )
      }

      QuarantineFailed = {
        Type  = "Fail"
        Error = "C2QuarantineFallbackFailed"

        Cause = (
          "C2 quarantine fallback did not complete successfully."
        )
      }
    }
  })

  logging_configuration {
    include_execution_data = true
    level                  = "ALL"

    log_destination = (
      "${aws_cloudwatch_log_group.c2_fallback.arn}:*"
    )
  }

  depends_on = [
    module.runtime_iam,
    aws_cloudwatch_log_group.c2_fallback
  ]
}
