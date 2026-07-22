# Data Lake Module

This module creates the S3 storage foundation for the thesis pipeline.

## Resources

- primary data-lake bucket
- separate Athena query-results bucket
- bucket-owner-enforced object ownership
- complete public-access blocking
- S3 versioning
- default AES256 server-side encryption
- HTTPS-only bucket policies
- lifecycle controls
- governed data-zone prefix markers

## Data zones

- `bronze/raw/olist/`
- `bronze/generated/`
- `silver/`
- `gold/internal/`
- `gold/public/`
- `quarantine/`
- `scripts/`
- `evidence/`
- `logs/`

Current data-lake objects are retained. Previous object versions expire
after the configured retention period. Athena query results expire
separately to control storage cost.
