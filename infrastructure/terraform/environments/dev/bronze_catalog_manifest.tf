locals {
  bronze_query_compatible_manifest_path = abspath(
    "${path.root}/../../../../manifests/bronze/olist/query-compatible-manifest.json"
  )

  bronze_query_compatible_manifest = jsondecode(
    file(local.bronze_query_compatible_manifest_path)
  )
}
