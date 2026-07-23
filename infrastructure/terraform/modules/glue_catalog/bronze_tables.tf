locals {
  bronze_query_compatible_tables = {
    for dataset in var.bronze_query_compatible_manifest.datasets :
    dataset.table_name => dataset
  }
}

resource "aws_glue_catalog_table" "bronze_query_compatible" {
  for_each = local.bronze_query_compatible_tables

  catalog_id    = var.aws_account_id
  database_name = aws_glue_catalog_database.this["bronze"].name
  name          = each.key
  table_type    = "EXTERNAL_TABLE"

  description = format(
    "Deterministic Olist query-compatible Bronze table for %s. Generated snapshot: %s.",
    each.key,
    var.bronze_query_compatible_manifest.generated_snapshot_id
  )

  parameters = {
    EXTERNAL              = "TRUE"
    classification        = "json"
    compressionType       = "none"
    typeOfData            = "file"
    managed_by            = "terraform"
    project               = var.project_name
    environment           = var.environment
    data_zone             = "bronze"
    source_system         = var.bronze_query_compatible_manifest.source_system
    source_snapshot_id    = var.bronze_query_compatible_manifest.source_snapshot_id
    generated_snapshot_id = var.bronze_query_compatible_manifest.generated_snapshot_id
    representation        = var.bronze_query_compatible_manifest.representation
    row_count             = tostring(each.value.row_count)
    object_size_bytes     = tostring(each.value.output_size_bytes)
    object_sha256         = each.value.output_sha256
  }

  storage_descriptor {
    location = replace(
      each.value.destination_location,
      "$${data_lake_bucket}",
      var.data_lake_bucket_name
    )

    input_format  = var.bronze_query_compatible_manifest.serde.input_format
    output_format = var.bronze_query_compatible_manifest.serde.output_format

    compressed                = false
    stored_as_sub_directories = false

    dynamic "columns" {
      for_each = each.value.columns

      content {
        name = columns.value.name
        type = columns.value.type
      }
    }

    ser_de_info {
      name = "${each.key}_json_serde"

      serialization_library = (
        var.bronze_query_compatible_manifest.serde.library
      )

      parameters = {}
    }
  }

  lifecycle {
    precondition {
      condition = (
        each.value.row_count > 0
        && each.value.output_size_bytes > 0
        && length(each.value.columns) > 0
      )

      error_message = "Bronze tables require positive rows and bytes and at least one column."
    }

    precondition {
      condition = alltrue([
        for column in each.value.columns :
        column.type == "string"
      ])

      error_message = "All raw Bronze columns must remain strings."
    }
  }
}
