data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  partition   = data.aws_partition.current.partition

  github_repository_parts = split("/", var.github_repository)
  github_owner            = local.github_repository_parts[0]
  github_repository_name  = local.github_repository_parts[1]

  github_oidc_host = "token.actions.githubusercontent.com"

  github_subject = (
    "repo:${local.github_owner}@${var.github_owner_id}/${local.github_repository_name}@${var.github_repository_id}:ref:refs/heads/${var.github_branch}"
  )

  glue_catalog_arn = (
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:catalog"
  )

  bronze_database_arn = (
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:database/${var.bronze_database_name}"
  )

  bronze_table_arn = (
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:table/${var.bronze_database_name}/*"
  )

  shadow_database_arn = (
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:database/${var.shadow_database_prefix}*"
  )

  shadow_table_arn = (
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:table/${var.shadow_database_prefix}*/*"
  )

  canonical_read_database_arns = [
    for database_name in var.canonical_read_database_names :
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:database/${database_name}"
  ]

  canonical_read_table_arns = [
    for database_name in var.canonical_read_database_names :
    "arn:${local.partition}:glue:${var.aws_region}:${var.aws_account_id}:table/${database_name}/*"
  ]

  athena_data_catalog_arn = (
    "arn:${local.partition}:athena:${var.aws_region}:${var.aws_account_id}:datacatalog/AwsDataCatalog"
  )

  data_lake_list_prefixes = [
    "bronze",
    "bronze/*",
    "silver",
    "silver/*",
    "gold",
    "gold/*",
    "experiments/c2",
    "experiments/c2/*"
  ]

  athena_results_list_prefixes = [
    "experiments/c2",
    "experiments/c2/*"
  ]

  bronze_object_arn = (
    "${var.data_lake_bucket_arn}/bronze/*"
  )

  shadow_data_object_arn = (
    "${var.data_lake_bucket_arn}/experiments/c2/*"
  )

  shadow_result_object_arn = (
    "${var.athena_results_bucket_arn}/experiments/c2/*"
  )
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    sid    = "AllowExactImmutableGitHubBranch"
    effect = "Allow"

    actions = [
      "sts:AssumeRoleWithWebIdentity"
    ]

    principals {
      type = "Federated"

      identifiers = [
        var.github_oidc_provider_arn
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_host}:aud"

      values = [
        "sts.amazonaws.com"
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_host}:sub"

      values = [
        local.github_subject
      ]
    }
  }
}

resource "aws_iam_role" "c2" {
  name = "${local.name_prefix}-github-c2"

  description = (
    "Immutable repository and branch scoped GitHub Actions role for isolated C2 Policy-as-Code validation."
  )

  assume_role_policy = (
    data.aws_iam_policy_document.github_assume_role.json
  )

  max_session_duration = 3600
}

data "aws_iam_policy_document" "c2" {
  statement {
    sid    = "ReadProjectBucketMetadata"
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
    sid    = "ListBronzeAndC2DataPrefixes"
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
    sid    = "ReadCanonicalBronzeObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion"
    ]

    resources = [
      local.bronze_object_arn
    ]
  }

  statement {
    sid    = "ManageIsolatedC2DataObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload"
    ]

    resources = [
      local.shadow_data_object_arn
    ]
  }

  statement {
    sid    = "ListIsolatedC2AthenaResults"
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
      values   = local.athena_results_list_prefixes
    }
  }

  statement {
    sid    = "ManageIsolatedC2AthenaResults"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload"
    ]

    resources = [
      local.shadow_result_object_arn
    ]
  }

  statement {
    sid    = "ReadBronzeAndShadowGlueMetadata"
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

    resources = concat(
      [
        local.glue_catalog_arn,
        local.bronze_database_arn,
        local.bronze_table_arn,
        local.shadow_database_arn,
        local.shadow_table_arn
      ],
      local.canonical_read_database_arns,
      local.canonical_read_table_arns
    )
  }

  statement {
    sid    = "CreateIsolatedC2GlueDatabases"
    effect = "Allow"

    actions = [
      "glue:CreateDatabase"
    ]

    resources = [
      local.glue_catalog_arn,
      local.shadow_database_arn
    ]
  }

  statement {
    sid    = "ManageIsolatedC2GlueDatabases"
    effect = "Allow"

    actions = [
      "glue:UpdateDatabase",
      "glue:DeleteDatabase"
    ]

    resources = [
      local.glue_catalog_arn,
      local.shadow_database_arn
    ]
  }

  statement {
    sid    = "ManageIsolatedC2GlueTables"
    effect = "Allow"

    actions = [
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

    resources = [
      local.glue_catalog_arn,
      local.shadow_database_arn,
      local.shadow_table_arn
    ]
  }

  statement {
    sid    = "RunQueriesOnlyInDbtWorkgroup"
    effect = "Allow"

    actions = [
      "athena:BatchGetQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetQueryRuntimeStatistics",
      "athena:GetWorkGroup",
      "athena:ListQueryExecutions",
      "athena:StartQueryExecution",
      "athena:StopQueryExecution"
    ]

    resources = [
      var.dbt_athena_workgroup_arn
    ]
  }

  statement {
    sid    = "ReadAwsDataCatalog"
    effect = "Allow"

    actions = [
      "athena:GetDataCatalog"
    ]

    resources = [
      local.athena_data_catalog_arn
    ]
  }

  statement {
    sid    = "StartC2FallbackStateMachine"
    effect = "Allow"

    actions = [
      "states:StartExecution"
    ]

    resources = [
      var.c2_fallback_state_machine_arn
    ]
  }

  statement {
    sid    = "ObserveC2FallbackExecutions"
    effect = "Allow"

    actions = [
      "states:DescribeExecution",
      "states:GetExecutionHistory",
      "states:StopExecution"
    ]

    resources = [
      "${replace(var.c2_fallback_state_machine_arn, ":stateMachine:", ":execution:")}:*"
    ]
  }

}

resource "aws_iam_policy" "c2" {
  name = "${local.name_prefix}-github-c2"

  description = (
    "Least-privilege Bronze read and isolated C2 Glue, S3 and Athena permissions."
  )

  policy = data.aws_iam_policy_document.c2.json
}

resource "aws_iam_role_policy_attachment" "c2" {
  role       = aws_iam_role.c2.name
  policy_arn = aws_iam_policy.c2.arn
}
