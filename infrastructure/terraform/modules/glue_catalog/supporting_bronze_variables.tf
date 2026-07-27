variable "bronze_supporting_manifest" {
  description = "Deterministic manifest defining the generated supporting Bronze dataset."

  type = object({
    schema_version            = string
    source_system             = string
    dataset_class             = string
    source_snapshot_id        = string
    generated_snapshot_id     = string
    representation            = string
    destination_prefix        = string
    manifest_destination_key  = string
    dataset_count             = number
    total_data_rows           = number
    total_output_size_bytes   = number

    governance = object({
      synthetic              = bool
      contains_real_pii      = bool
      contains_simulated_pii = bool
    })

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
      primary_key          = list(string)

      columns = list(object({
        name = string
        type = string
      }))
    }))
  })

  validation {
    condition = (
      var.bronze_supporting_manifest.schema_version == "1.0"
      && var.bronze_supporting_manifest.source_system
      == "olist-derived-synthetic-supporting"
      && var.bronze_supporting_manifest.dataset_class
      == "generated_supporting_data"
      && var.bronze_supporting_manifest.dataset_count == 1
      && length(var.bronze_supporting_manifest.datasets) == 1
      && var.bronze_supporting_manifest.total_data_rows == 99441
      && var.bronze_supporting_manifest.total_output_size_bytes == 30976008
    )

    error_message = "The supporting Bronze manifest identity or approved totals are invalid."
  }

  validation {
    condition = (
      var.bronze_supporting_manifest.source_snapshot_id
      == "43cc5e9c8436f7919491dd90872d6f4d94d61d4694c1d4307e41456e405052d2"
      && var.bronze_supporting_manifest.generated_snapshot_id
      == "1b7972218afd4016928dfb185f7eff30dd2a612384b357beae24bf8daac44e2c"
    )

    error_message = "The supporting Bronze snapshot identifiers are not the approved deterministic values."
  }

  validation {
    condition = (
      var.bronze_supporting_manifest.destination_prefix
      == "bronze/generated/supporting/synthetic-customer-contact/snapshots/${var.bronze_supporting_manifest.generated_snapshot_id}"
      && var.bronze_supporting_manifest.manifest_destination_key
      == "${var.bronze_supporting_manifest.destination_prefix}/synthetic-customer-contact-manifest.json"
    )

    error_message = "The supporting Bronze immutable destination prefix or completion-manifest key is invalid."
  }

  validation {
    condition = (
      var.bronze_supporting_manifest.representation
      == "athena-json-lines"
      && var.bronze_supporting_manifest.serde.library
      == "org.apache.hive.hcatalog.data.JsonSerDe"
      && var.bronze_supporting_manifest.serde.input_format
      == "org.apache.hadoop.mapred.TextInputFormat"
      && var.bronze_supporting_manifest.serde.output_format
      == "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    )

    error_message = "The supporting dataset must use the approved Athena JSON Lines and Hive JSON SerDe configuration."
  }

  validation {
    condition = (
      var.bronze_supporting_manifest.governance.synthetic
      && !var.bronze_supporting_manifest.governance.contains_real_pii
      && var.bronze_supporting_manifest.governance.contains_simulated_pii
    )

    error_message = "The supporting dataset governance classification is invalid."
  }

  validation {
    condition = try(
      var.bronze_supporting_manifest.datasets[0].table_name
      == "synthetic_customer_contact"
      && var.bronze_supporting_manifest.datasets[0].row_count
      == 99441
      && var.bronze_supporting_manifest.datasets[0].output_size_bytes
      == 20509734
      && var.bronze_supporting_manifest.datasets[0].output_sha256
      == "9585db5f832eafdfff201262037de50cf2713bdb5b7f83366ddc150988e535c4"
      && length(
        var.bronze_supporting_manifest.datasets[0].primary_key
      ) == 1
      && var.bronze_supporting_manifest.datasets[0].primary_key[0]
      == "customer_id",
      false
    )

    error_message = "The supporting Bronze table identity, row count, object size, checksum or primary key is invalid."
  }

  validation {
    condition = try(
      [
        for column in var.bronze_supporting_manifest.datasets[0].columns :
        "${column.name}:${column.type}"
      ] == [
        "customer_id:string",
        "synthetic_email:string",
        "synthetic_phone:string",
        "marketing_consent:boolean",
        "pii_classification:string",
      ],
      false
    )

    error_message = "The supporting Bronze schema is not the approved five-column schema."
  }

  validation {
    condition = try(
      var.bronze_supporting_manifest.datasets[0].destination_location
      == "s3://$${data_lake_bucket}/${var.bronze_supporting_manifest.destination_prefix}/tables/synthetic_customer_contact/"
      && can(regex(
        "^[0-9a-f]{64}$",
        var.bronze_supporting_manifest.datasets[0].output_sha256
      )),
      false
    )

    error_message = "The supporting Bronze table location or object checksum is invalid."
  }
}
