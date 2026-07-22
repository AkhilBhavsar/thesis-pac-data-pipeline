# Athena Module

This module creates the governed Athena SQL workgroup used by the thesis
pipeline.

## Controls

- workgroup configuration overrides client-side settings
- encrypted S3 query-result storage
- expected bucket-owner verification
- CloudWatch metrics enabled
- automatic Athena engine selection
- 1 GiB per-query scan cutoff

The default `primary` workgroup remains unchanged. Project queries must
use the Terraform-managed thesis workgroup.
