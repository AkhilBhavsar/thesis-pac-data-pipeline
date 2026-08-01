resource "aws_glue_catalog_table" "quarantine_events" {
  catalog_id    = var.aws_account_id
  database_name = aws_glue_catalog_database.this["quarantine"].name
  name          = "quarantine_events"
  table_type    = "EXTERNAL_TABLE"

  description = "Governed control records for policy-quarantined pipeline outputs and bounded remediation."

  parameters = {
    EXTERNAL              = "TRUE"
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
    project               = var.project_name
    environment           = var.environment
    data_zone             = "quarantine"
    object_kind           = "quarantine-control-event"
  }

  storage_descriptor {
    location = "s3://${var.data_lake_bucket_name}/quarantine/events/"

    input_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"

    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    compressed = true

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"

      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "quarantine_event_id"
      type = "string"
    }

    columns {
      name = "run_id"
      type = "string"
    }

    columns {
      name = "scenario_id"
      type = "string"
    }

    columns {
      name = "source_dataset"
      type = "string"
    }

    columns {
      name = "source_relation"
      type = "string"
    }

    columns {
      name = "rejected_output_location"
      type = "string"
    }

    columns {
      name = "policy_category"
      type = "string"
    }

    columns {
      name = "policy_id"
      type = "string"
    }

    columns {
      name = "violation_code"
      type = "string"
    }

    columns {
      name = "violation_details"
      type = "string"
    }

    columns {
      name = "data_classification"
      type = "string"
    }

    columns {
      name = "detected_at"
      type = "timestamp"
    }

    columns {
      name = "quarantined_at"
      type = "timestamp"
    }

    columns {
      name = "remediation_action"
      type = "string"
    }

    columns {
      name = "remediation_status"
      type = "string"
    }

    columns {
      name = "retry_count"
      type = "bigint"
    }

    columns {
      name = "max_retries"
      type = "bigint"
    }

    columns {
      name = "manual_review_required"
      type = "boolean"
    }

    columns {
      name = "manual_review_status"
      type = "string"
    }

    columns {
      name = "release_status"
      type = "string"
    }

    columns {
      name = "released_at"
      type = "timestamp"
    }

    columns {
      name = "final_state"
      type = "string"
    }

    columns {
      name = "evidence_uri"
      type = "string"
    }
  }
}
