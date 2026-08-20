data "aws_iam_policy_document" "c2_quarantine_runtime" {
  statement {
    sid    = "ReadC2QuarantineBucketMetadata"
    effect = "Allow"

    actions = [
      "s3:GetBucketLocation"
    ]

    resources = [
      var.data_lake_bucket_arn,
      var.athena_results_bucket_arn
    ]
  }

  statement {
    sid    = "ListC2QuarantineDataLakePrefixes"
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

      values = [
        "experiments/c2",
        "experiments/c2/*",
        "quarantine",
        "quarantine/*"
      ]
    }
  }

  statement {
    sid    = "ListC2AthenaResults"
    effect = "Allow"

    actions = [
      "s3:ListBucket"
    ]

    resources = [
      var.athena_results_bucket_arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"

      values = [
        "results",
        "results/*"
      ]
    }
  }

  statement {
    sid    = "ReadDeleteC2ExperimentObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:DeleteObject"
    ]

    resources = [
      "${var.data_lake_bucket_arn}/experiments/c2/*"
    ]
  }

  statement {
    sid    = "ManageC2QuarantineObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload"
    ]

    resources = [
      "${var.data_lake_bucket_arn}/quarantine/*"
    ]
  }

  statement {
    sid    = "ManageC2AthenaResultObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload"
    ]

    resources = [
      "${var.athena_results_bucket_arn}/results/*"
    ]
  }

  statement {
    sid    = "ReadC2QuarantineGlueMetadata"
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
      "glue:BatchGetPartition"
    ]

    resources = [
      local.glue_catalog_arn,
      "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:database/${var.glue_database_names["quarantine"]}",
      "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:table/${var.glue_database_names["quarantine"]}/*"
    ]
  }

  statement {
    sid    = "RunC2QuarantineAthenaWrites"
    effect = "Allow"

    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup"
    ]

    resources = [
      var.athena_workgroup_arn
    ]
  }
}
