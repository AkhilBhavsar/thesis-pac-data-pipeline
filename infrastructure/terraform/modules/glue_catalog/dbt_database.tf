resource "aws_glue_catalog_database" "dbt" {
  catalog_id = var.aws_account_id

  name = replace(
    "${var.project_name}_${var.environment}_dbt",
    "-",
    "_"
  )

  description  = "Development database for controlled dbt transformations."
  location_uri = "s3://${var.data_lake_bucket_name}/dbt/${var.environment}/"

  parameters = {
    project     = var.project_name
    environment = var.environment
    data_zone   = "dbt"
    managed_by  = "terraform"
    purpose     = "controlled_transformation"
  }
}
