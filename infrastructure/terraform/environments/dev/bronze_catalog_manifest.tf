locals {
  bronze_query_compatible_manifest_path = abspath(
    "${path.root}/../../../../manifests/bronze/olist/query-compatible-manifest.json"
  )

  bronze_query_compatible_manifest = jsondecode(
    file(local.bronze_query_compatible_manifest_path)
  )

  bronze_supporting_manifest_path = abspath(
    "${path.root}/../../../../manifests/bronze/supporting/synthetic-customer-contact-manifest.json"
  )

  bronze_supporting_manifest = jsondecode(
    file(local.bronze_supporting_manifest_path)
  )
}
