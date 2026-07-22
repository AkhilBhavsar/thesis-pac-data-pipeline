locals {
  databases = {
    bronze = {
      suffix       = "bronze"
      description  = "Raw and generated Bronze-zone datasets."
      location_uri = "s3://${var.data_lake_bucket_name}/bronze/"
    }

    silver = {
      suffix       = "silver"
      description  = "Cleaned and standardised Silver-zone datasets."
      location_uri = "s3://${var.data_lake_bucket_name}/silver/"
    }

    gold_internal = {
      suffix       = "gold_internal"
      description  = "Governed internal Gold analytics datasets."
      location_uri = "s3://${var.data_lake_bucket_name}/gold/internal/"
    }

    gold_public = {
      suffix       = "gold_public"
      description  = "Public-safe Gold analytics datasets."
      location_uri = "s3://${var.data_lake_bucket_name}/gold/public/"
    }

    quarantine = {
      suffix       = "quarantine"
      description  = "Rejected or policy-quarantined pipeline outputs."
      location_uri = "s3://${var.data_lake_bucket_name}/quarantine/"
    }
  }
}

resource "aws_glue_catalog_database" "this" {
  for_each = local.databases

  catalog_id   = var.aws_account_id
  name         = replace("${var.project_name}_${var.environment}_${each.value.suffix}", "-", "_")
  description  = each.value.description
  location_uri = each.value.location_uri

  parameters = {
    project     = var.project_name
    environment = var.environment
    data_zone   = each.key
    managed_by  = "terraform"
  }
}
