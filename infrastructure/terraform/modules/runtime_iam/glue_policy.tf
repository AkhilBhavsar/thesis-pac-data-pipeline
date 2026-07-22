data "aws_iam_policy_document" "glue_runtime" {
  statement {
    sid    = "ReadDataLakeBucketMetadata"
    effect = "Allow"

    actions = [
      "s3:GetBucketLocation"
    ]

    resources = [
      var.data_lake_bucket_arn
    ]
  }

  statement {
    sid    = "ListGovernedDataLakePrefixes"
    effect = "Allow"

    actions = [
      "s3:ListBucket"
    ]

    resources = [
      var.data_lake_bucket_arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = local.data_lake_list_prefixes
    }
  }

  statement {
    sid    = "ReadWriteGovernedDataLakeObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload"
    ]

    resources = local.data_lake_object_arns
  }

  statement {
    sid    = "ManageThesisGlueCatalogMetadata"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetTableVersion",
      "glue:GetTableVersions",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:BatchUpdatePartition",
      "glue:DeletePartition",
      "glue:BatchDeletePartition"
    ]

    resources = local.glue_catalog_resources
  }

  statement {
    sid    = "WriteGlueRuntimeLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:${local.partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws-glue/*",
      "arn:${local.partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws-glue/*:*"
    ]
  }

  statement {
    sid    = "PublishGlueRuntimeMetrics"
    effect = "Allow"

    actions = [
      "cloudwatch:PutMetricData"
    ]

    resources = ["*"]
  }
}
