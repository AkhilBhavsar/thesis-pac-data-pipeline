# Cost Controls Module

This module validates existing account-level AWS Budgets without
creating duplicate budget resources.

## Existing account budgets

### My Zero-Spend Budget

- monthly COST budget
- USD 0.01 limit
- actual-spend notification

### My Monthly Cost Budget

- monthly COST budget
- USD 2.00 limit
- actual and forecasted-spend notifications

## Infrastructure-level cost controls

Additional protections are implemented by the AWS foundation:

- Athena 1 GiB per-query scan cutoff
- enforced Athena workgroup configuration
- Athena query-result expiration after 30 days
- S3 incomplete multipart-upload cleanup
- S3 noncurrent-version retention
- default project and environment resource tags

The account budgets remain externally managed. Terraform reads and
validates them but does not create, modify, import or destroy them.

Project cost-allocation tag keys will be activated after AWS makes the
recently applied tag keys available through Billing and Cost Management.

The Terraform data source validates the budget type, currency and limit.
The monthly cadence and notification thresholds are independently
verified through AWS CLI foundation-validation evidence because the
provider data-source response does not currently populate `time_unit`
for these existing budgets.
