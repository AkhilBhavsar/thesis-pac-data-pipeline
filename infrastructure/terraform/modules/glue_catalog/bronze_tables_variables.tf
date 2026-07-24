variable "bronze_query_compatible_manifest" {
  description = "Deterministic manifest defining the query-compatible Olist Bronze tables."
  type = object({
    source_system                      = string
    source_snapshot_id                 = string
    generated_snapshot_id              = string
    representation                     = string
    destination_prefix                 = string
    dataset_count                      = number
    total_data_rows                    = number
    total_output_size_bytes            = number
    total_records_with_embedded_breaks = number

    serde = object({
      library       = string
      input_format  = string
      output_format = string
    })

    datasets = list(object({
      table_name           = string
      destination_location = string
      row_count            = number
      output_size_bytes    = number
      output_sha256        = string

      columns = list(object({
        name = string
        type = string
      }))
    }))
  })

  validation {
    condition = (
      var.bronze_query_compatible_manifest.dataset_count
      == length(var.bronze_query_compatible_manifest.datasets)
    )

    error_message = "dataset_count must equal the number of datasets in the manifest."
  }

  validation {
    condition = (
      var.bronze_query_compatible_manifest.dataset_count == 9
      && var.bronze_query_compatible_manifest.total_data_rows == 1550922
      && var.bronze_query_compatible_manifest.total_output_size_bytes == 314973186
      && var.bronze_query_compatible_manifest.total_records_with_embedded_breaks == 3852
    )

    error_message = "The query-compatible Bronze manifest totals are not the approved deterministic values."
  }

  validation {
    condition = (
      can(regex(
        "^[0-9a-f]{64}$",
        var.bronze_query_compatible_manifest.source_snapshot_id
      ))
      && can(regex(
        "^[0-9a-f]{64}$",
        var.bronze_query_compatible_manifest.generated_snapshot_id
      ))
    )

    error_message = "Both snapshot identifiers must be lowercase 64-character SHA-256 values."
  }

  validation {
    condition = (
      var.bronze_query_compatible_manifest.representation
      == "athena-json-lines"
      && var.bronze_query_compatible_manifest.serde.library
      == "org.apache.hive.hcatalog.data.JsonSerDe"
      && var.bronze_query_compatible_manifest.serde.input_format
      == "org.apache.hadoop.mapred.TextInputFormat"
      && var.bronze_query_compatible_manifest.serde.output_format
      == "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    )

    error_message = "The manifest must use the approved Athena JSON Lines and Hive JSON SerDe configuration."
  }

  validation {
    condition = (
      length(distinct([
        for dataset in var.bronze_query_compatible_manifest.datasets :
        dataset.table_name
      ]))
      == length(var.bronze_query_compatible_manifest.datasets)
    )

    error_message = "Every Bronze table name must be unique."
  }

  validation {
    condition = alltrue([
      for dataset in var.bronze_query_compatible_manifest.datasets :
      length(dataset.columns) > 0
      && dataset.row_count > 0
      && dataset.output_size_bytes > 0
      && can(regex("^[0-9a-f]{64}$", dataset.output_sha256))
      && startswith(
        dataset.destination_location,
        "s3://$${data_lake_bucket}/"
      )
      && endswith(dataset.destination_location, "/")
      && alltrue([
        for column in dataset.columns :
        column.type == "string"
        && can(regex("^[a-z][a-z0-9_]*$", column.name))
      ])
    ])

    error_message = "Every dataset must have a valid location, checksum, positive size and row count, and non-empty string columns."
  }
}
