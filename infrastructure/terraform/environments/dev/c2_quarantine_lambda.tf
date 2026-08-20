locals {
  c2_quarantine_function_name = (
    "${var.project_name}-${var.environment}-c2-quarantine"
  )
}

data "archive_file" "c2_quarantine" {
  type = "zip"

  source_file = (
    "${path.module}/../../../../runtime/lambda/quarantine/lambda_handler.py"
  )

  output_path = (
    "${path.module}/.terraform/c2-quarantine-lambda.zip"
  )
}

resource "aws_cloudwatch_log_group" "c2_quarantine" {
  name = (
    "/aws/lambda/${local.c2_quarantine_function_name}"
  )

  retention_in_days = 14
}

resource "aws_lambda_function" "c2_quarantine" {
  function_name = local.c2_quarantine_function_name

  description = (
    "C2 bounded-remediation quarantine runtime for isolated rejected outputs."
  )

  role = module.runtime_iam.role_arns["lambda"]

  runtime = "python3.12"
  handler = "lambda_handler.lambda_handler"

  filename = (
    data.archive_file.c2_quarantine.output_path
  )

  source_code_hash = (
    data.archive_file.c2_quarantine.output_base64sha256
  )

  memory_size = 256
  timeout     = 60

  environment {
    variables = {
      DATA_LAKE_BUCKET = (
        module.data_lake.data_lake_bucket_name
      )

      QUARANTINE_DATABASE = (
        module.glue_catalog.database_names["quarantine"]
      )

      QUARANTINE_TABLE = "quarantine_events"

      ATHENA_WORKGROUP = (
        module.athena.workgroup_name
      )
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.c2_quarantine
  ]
}
