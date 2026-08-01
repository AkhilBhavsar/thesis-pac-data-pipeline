output "bronze_supporting_table_names" {
  description = "Generated supporting Bronze Glue table names."

  value = (
    module.glue_catalog.bronze_supporting_table_names
  )
}

output "bronze_supporting_table_locations" {
  description = "Generated supporting Bronze Glue table S3 locations."

  value = (
    module.glue_catalog.bronze_supporting_table_locations
  )
}

output "bronze_supporting_generated_snapshot_id" {
  description = "Generated supporting Bronze snapshot registered in Glue."

  value = (
    module.glue_catalog.bronze_supporting_generated_snapshot_id
  )
}

output "all_bronze_table_names" {
  description = "All governed Bronze Glue table names."

  value = (
    module.glue_catalog.all_bronze_table_names
  )
}

output "all_bronze_table_count" {
  description = "Total governed Bronze Glue table count."

  value = (
    module.glue_catalog.all_bronze_table_count
  )
}
