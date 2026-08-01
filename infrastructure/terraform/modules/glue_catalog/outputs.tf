output "database_names" {
  description = "Glue Data Catalog database names by governed data zone."

  value = {
    for zone, database in aws_glue_catalog_database.this :
    zone => database.name
  }
}

output "database_ids" {
  description = "Glue Data Catalog database identifiers by governed data zone."

  value = {
    for zone, database in aws_glue_catalog_database.this :
    zone => database.id
  }
}

output "dbt_database_name" {
  description = "Glue database used for controlled dbt transformations."
  value       = aws_glue_catalog_database.dbt.name
}

output "dbt_database_id" {
  description = "Identifier of the controlled dbt Glue database."
  value       = aws_glue_catalog_database.dbt.id
}
