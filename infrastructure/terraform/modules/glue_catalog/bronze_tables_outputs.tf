output "bronze_query_compatible_table_names" {
  description = "Deterministic query-compatible Bronze table names."
  value = sort(
    keys(aws_glue_catalog_table.bronze_query_compatible)
  )
}

output "bronze_query_compatible_table_locations" {
  description = "S3 locations used by the query-compatible Bronze tables."

  value = {
    for table_name, dataset in local.bronze_query_compatible_tables :
    table_name => replace(
      dataset.destination_location,
      "$${data_lake_bucket}",
      var.data_lake_bucket_name
    )
  }
}

output "bronze_query_compatible_generated_snapshot_id" {
  description = "Generated snapshot registered in the Bronze Glue tables."
  value       = var.bronze_query_compatible_manifest.generated_snapshot_id
}
