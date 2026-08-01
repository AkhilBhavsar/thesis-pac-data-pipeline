output "bronze_supporting_table_names" {
  description = "Deterministic generated supporting Bronze table names."

  value = sort(
    keys(
      aws_glue_catalog_table.bronze_supporting
    )
  )
}

output "bronze_supporting_table_locations" {
  description = "S3 locations used by the generated supporting Bronze tables."

  value = {
    for table_name, dataset in local.bronze_supporting_tables :
    table_name => replace(
      dataset.destination_location,
      "$${data_lake_bucket}",
      var.data_lake_bucket_name
    )
  }
}

output "bronze_supporting_generated_snapshot_id" {
  description = "Generated supporting Bronze snapshot registered in Glue."

  value = (
    var.bronze_supporting_manifest.generated_snapshot_id
  )
}

output "all_bronze_table_names" {
  description = "All governed query-compatible and supporting Bronze tables."

  value = sort(
    concat(
      keys(
        aws_glue_catalog_table.bronze_query_compatible
      ),
      keys(
        aws_glue_catalog_table.bronze_supporting
      )
    )
  )
}

output "all_bronze_table_count" {
  description = "Total number of governed Bronze Glue tables."

  value = (
    length(
      aws_glue_catalog_table.bronze_query_compatible
    )
    + length(
      aws_glue_catalog_table.bronze_supporting
    )
  )
}
