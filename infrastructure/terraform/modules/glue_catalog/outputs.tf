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
