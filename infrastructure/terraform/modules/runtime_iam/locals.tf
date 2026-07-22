data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  partition   = data.aws_partition.current.partition

  data_lake_prefix_roots = [
    "bronze",
    "silver",
    "gold",
    "quarantine",
    "scripts",
    "evidence",
    "logs"
  ]

  data_lake_list_prefixes = flatten([
    for prefix in local.data_lake_prefix_roots : [
      prefix,
      "${prefix}/*"
    ]
  ])

  data_lake_object_arns = [
    for prefix in local.data_lake_prefix_roots :
    "${var.data_lake_bucket_arn}/${prefix}/*"
  ]

  athena_results_object_arn = "${var.athena_results_bucket_arn}/results/*"

  glue_catalog_arn = "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:catalog"

  glue_database_arns = [
    for database_name in values(var.glue_database_names) :
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:database/${database_name}"
  ]

  glue_table_arns = [
    for database_name in values(var.glue_database_names) :
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:table/${database_name}/*"
  ]

  glue_catalog_resources = concat(
    [local.glue_catalog_arn],
    local.glue_database_arns,
    local.glue_table_arns
  )

  project_lambda_function_arns = [
    "arn:${local.partition}:lambda:${var.aws_region}:${var.aws_account_id}:function:${local.name_prefix}-*",
    "arn:${local.partition}:lambda:${var.aws_region}:${var.aws_account_id}:function:${local.name_prefix}-*:*"
  ]
}
