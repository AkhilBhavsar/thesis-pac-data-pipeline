# Runtime IAM Module

This module creates separate execution roles for the cloud-native
thesis data pipeline.

## Runtime roles

- AWS Glue ETL runtime
- Lambda validation and bounded-remediation runtime
- Step Functions orchestration runtime

## Glue permissions

The Glue runtime role can:

- read and write objects in the thesis data-lake bucket
- list only the governed data-zone prefixes
- read and manage tables and partitions in the thesis Glue databases
- publish Glue runtime logs and metrics

## Lambda permissions

The Lambda runtime role can:

- read and write governed data-lake objects
- manage objects in the Athena results prefix
- read thesis Glue Catalog metadata
- execute queries through the governed Athena workgroup
- publish standard Lambda execution logs

## Step Functions permissions

The Step Functions role can:

- start and monitor Glue job runs
- invoke only Lambda functions using the thesis project prefix
- publish workflow execution logs

Each AWS service receives a separate trust policy. A Glue job cannot
assume the Lambda or Step Functions roles, and the other services cannot
assume the Glue role.

Permissions should be expanded only when a later pipeline component
demonstrates a specific additional runtime requirement.
