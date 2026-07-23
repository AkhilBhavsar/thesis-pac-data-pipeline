# AWS Foundation Validation

- Run ID: `aws-foundation-20260723T183709Z`
- Generated: `2026-07-23T18:37:09.730081+00:00`
- Git branch: `feature/aws-foundation-validation`
- Git commit: `daec437a49d55c3a05b7ddfe80143242007c5d9b`
- AWS account: `522814714524`
- AWS region: `eu-west-1`
- Overall status: **PASS**
- PASS: **54**
- FAIL: **0**
- PENDING: **0**

## Validation checks

| Status | Check | Details |
|---|---|---|
| PASS | AWS account | Resolved account 522814714524; expected 522814714524. |
| PASS | AWS region | Resolved region eu-west-1; expected eu-west-1. |
| PASS | Terraform validation | Terraform configuration is valid. |
| PASS | Terraform drift | No managed-resource or output changes detected. |
| PASS | Terraform managed-resource count | Found 40 managed resources; expected 40. |
| PASS | Terraform state public-access block | All four public-access controls are enabled for thesis-pac-terraform-state-522814714524-eu-west-1. |
| PASS | Terraform state encryption | Encryption algorithm is AES256; expected AES256. |
| PASS | Terraform state versioning | Versioning status is Enabled. |
| PASS | Terraform state ownership | Ownership mode is BucketOwnerEnforced. |
| PASS | Terraform state HTTPS-only policy | Bucket policy denies requests when aws:SecureTransport is false. |
| PASS | Terraform state lifecycle | {"abort_days": 7, "noncurrent_days": 90} |
| PASS | Data lake public-access block | All four public-access controls are enabled for thesis-pac-dev-data-lake-522814714524-eu-west-1. |
| PASS | Data lake encryption | Encryption algorithm is AES256; expected AES256. |
| PASS | Data lake versioning | Versioning status is Enabled. |
| PASS | Data lake ownership | Ownership mode is BucketOwnerEnforced. |
| PASS | Data lake HTTPS-only policy | Bucket policy denies requests when aws:SecureTransport is false. |
| PASS | Data lake lifecycle | {"abort_days": 7, "noncurrent_days": 90} |
| PASS | Athena results public-access block | All four public-access controls are enabled for thesis-pac-dev-athena-results-522814714524-eu-west-1. |
| PASS | Athena results encryption | Encryption algorithm is AES256; expected AES256. |
| PASS | Athena results versioning | Versioning status is Enabled. |
| PASS | Athena results ownership | Ownership mode is BucketOwnerEnforced. |
| PASS | Athena results HTTPS-only policy | Bucket policy denies requests when aws:SecureTransport is false. |
| PASS | Athena results lifecycle | {"expiration_days": 30} |
| PASS | Remote development-state object | size=150410 bytes, encryption=AES256, versioned=True. |
| PASS | S3 prefix marker bronze/generated/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker bronze/raw/olist/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker evidence/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker gold/internal/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker gold/public/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker logs/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker quarantine/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker scripts/ | Marker exists with size 0 bytes. |
| PASS | S3 prefix marker silver/ | Marker exists with size 0 bytes. |
| PASS | Glue database bronze | Resolved database thesis_pac_dev_bronze. |
| PASS | Glue database gold_internal | Resolved database thesis_pac_dev_gold_internal. |
| PASS | Glue database gold_public | Resolved database thesis_pac_dev_gold_public. |
| PASS | Glue database quarantine | Resolved database thesis_pac_dev_quarantine. |
| PASS | Glue database silver | Resolved database thesis_pac_dev_silver. |
| PASS | Athena governed workgroup | state=ENABLED, enforced=True, metrics=True, cutoff=1073741824, encryption=SSE_S3. |
| PASS | Budget configuration: My Monthly Cost Budget | limit=2.0 USD. |
| PASS | Budget notifications: My Monthly Cost Budget | Observed 3 rules. |
| PASS | Budget configuration: My Zero-Spend Budget | limit=0.01 USD. |
| PASS | Budget notifications: My Zero-Spend Budget | Observed 1 rules. |
| PASS | Project budget configuration | name=thesis-pac-dev-project-budget, limit=2.00 USD, scope={'Environment': 'dev', 'Project': 'thesis-pac'}. |
| PASS | Project budget notifications | Observed the expected five project-budget alert rules. |
| PASS | Cost-allocation tags | All four tags are active. |
| PASS | Current-month account AWS cost | Account cost is USD 0.0511758034; monthly account limit is USD 2.00. Zero-spend threshold USD 0.01 has been crossed. |
| PASS | Current-month project AWS cost | Tagged project cost is USD 0.0000000000; project budget limit is USD 2.00. |
| PASS | IAM trust policy: glue | Role AWSGlueServiceRole-thesis-pac-dev-runtime. |
| PASS | IAM policy attachments: glue | Attached policies=['thesis-pac-dev-glue-runtime']. |
| PASS | IAM trust policy: lambda | Role thesis-pac-dev-lambda-runtime. |
| PASS | IAM policy attachments: lambda | Attached policies=['AWSLambdaBasicExecutionRole', 'thesis-pac-dev-lambda-runtime']. |
| PASS | IAM trust policy: step_functions | Role thesis-pac-dev-step-functions-runtime. |
| PASS | IAM policy attachments: step_functions | Attached policies=['thesis-pac-dev-step-functions-runtime']. |

## Interpretation

The AWS foundation passes when no checks are marked `FAIL`. Cost-allocation tags may remain `PENDING` while AWS Billing propagates recently applied tag keys.

## Supporting evidence

- `aws-foundation-validation.json`
- `terraform-drift-plan.txt`
