# Glue Catalog Module

This module creates governed AWS Glue Data Catalog databases for the
cloud-native thesis pipeline.

## Databases

- Bronze
- Silver
- Gold Internal
- Gold Public-Safe
- Quarantine

Each database has a default S3 location aligned with the corresponding
data-lake zone. Tables will be registered in later pipeline phases after
the Bronze ingestion and Glue transformations are implemented.
