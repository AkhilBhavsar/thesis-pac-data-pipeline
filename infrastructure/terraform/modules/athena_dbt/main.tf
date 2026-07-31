locals {
  workgroup_name = "${var.project_name}-${var.environment}-dbt-transform"
}

resource "aws_athena_workgroup" "this" {
  name        = local.workgroup_name
  description = "Dedicated Athena workgroup for dbt transformations."
  state       = "ENABLED"

  configuration {
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_cutoff_per_query
    enforce_workgroup_configuration    = false
    publish_cloudwatch_metrics_enabled = true

    engine_version {
      selected_engine_version = "AUTO"
    }
  }
}
