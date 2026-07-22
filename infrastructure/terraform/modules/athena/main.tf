locals {
  workgroup_name = "${var.project_name}-${var.environment}-analytics"
}

resource "aws_athena_workgroup" "this" {
  name        = local.workgroup_name
  description = "Governed Athena workgroup for the cloud-native thesis pipeline."
  state       = "ENABLED"

  configuration {
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_cutoff_per_query
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    engine_version {
      selected_engine_version = "AUTO"
    }

    result_configuration {
      output_location       = var.results_location
      expected_bucket_owner = var.expected_bucket_owner

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
