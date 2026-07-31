locals {
  bronze_supporting_tables = {
    for dataset in var.bronze_supporting_manifest.datasets :
    dataset.table_name => dataset
  }
}

resource "aws_glue_catalog_table" "bronze_supporting" {
  for_each = local.bronze_supporting_tables

  catalog_id    = var.aws_account_id
  database_name = aws_glue_catalog_database.this["bronze"].name
  name          = each.key
  table_type    = "EXTERNAL_TABLE"

  description = format(
    "Deterministic generated supporting Bronze table for %s. Generated snapshot: %s.",
    each.key,
    var.bronze_supporting_manifest.generated_snapshot_id
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
    source_system         = var.bronze_supporting_manifest.source_system
    dataset_class         = var.bronze_supporting_manifest.dataset_class
    source_snapshot_id    = var.bronze_supporting_manifest.source_snapshot_id
    generated_snapshot_id = var.bronze_supporting_manifest.generated_snapshot_id
    representation        = var.bronze_supporting_manifest.representation
    row_count             = tostring(each.value.row_count)
    object_size_bytes     = tostring(each.value.output_size_bytes)
    object_sha256         = each.value.output_sha256
    primary_key           = join(",", each.value.primary_key)
    synthetic             = tostring(var.bronze_supporting_manifest.governance.synthetic)
    contains_real_pii     = tostring(var.bronze_supporting_manifest.governance.contains_real_pii)
    contains_simulated_pii = tostring(
      var.bronze_supporting_manifest.governance.contains_simulated_pii
    )
  }

  storage_descriptor {
    location = replace(
      each.value.destination_location,
      "$${data_lake_bucket}",
      var.data_lake_bucket_name
    )

    input_format  = var.bronze_supporting_manifest.serde.input_format
    output_format = var.bronze_supporting_manifest.serde.output_format

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
        var.bronze_supporting_manifest.serde.library
      )

      parameters = {}
    }
  }

  lifecycle {
    precondition {
      condition = (
        each.key == "synthetic_customer_contact"
        && each.value.row_count == 99441
        && each.value.output_size_bytes == 20509734
        && each.value.output_sha256
        == "9585db5f832eafdfff201262037de50cf2713bdb5b7f83366ddc150988e535c4"
      )

      error_message = "The supporting Bronze Glue table does not reference the approved immutable dataset."
    }

    precondition {
      condition = (
        length(each.value.columns) == 5
        && length([
          for column in each.value.columns :
          column
          if column.type == "boolean"
        ]) == 1
        && length([
          for column in each.value.columns :
          column
          if column.name == "marketing_consent"
          && column.type == "boolean"
        ]) == 1
      )

      error_message = "marketing_consent must be the only Boolean field in the five-column supporting Bronze schema."
    }

    precondition {
      condition = (
        var.bronze_supporting_manifest.governance.synthetic
        && !var.bronze_supporting_manifest.governance.contains_real_pii
        && var.bronze_supporting_manifest.governance.contains_simulated_pii
      )

      error_message = "The supporting Bronze governance classification must identify synthetic simulated PII and no real PII."
    }
  }
}
