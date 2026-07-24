# AWS Bronze Catalog Validation Evidence

- Overall status: **PASS**
- Generated at: `2026-07-23T23:58:51Z`
- Branch: `feature/aws-bronze-catalog`
- Commit: `6d1ed2c27d9be5c6228ac0049fad65ee4984fa7d`
- AWS account: `522814714524`
- Region: `eu-west-1`
- Glue database: `thesis_pac_dev_bronze`
- Generated snapshot: `921334afa3174398562e25bf51a14b8b74692b64053d1f8728dec259ac93b5c5`
- Manifest SHA-256: `ba7579a17f904fe60b7fbbb14186ff38962030af419014d7593eeabefb2d14d9`

## Terraform

- Apply: **9 added, 0 changed, 0 destroyed**
- Terraform-managed Bronze tables: **9**
- Post-apply drift: **none**
- Approved plan SHA-256: `23f14f7e4a482e9c07105a676799d5ebdd66562c0c99267a9ecb91e489ce2d16`

## Glue and Athena validation

| Table | Columns | Expected rows | Athena rows |
|---|---:|---:|---:|
| olist_customers | 5 | 99441 | 99441 |
| olist_geolocation | 5 | 1000163 | 1000163 |
| olist_order_items | 7 | 112650 | 112650 |
| olist_order_payments | 5 | 103886 | 103886 |
| olist_order_reviews | 7 | 99224 | 99224 |
| olist_orders | 8 | 99441 | 99441 |
| olist_product_category_name_translation | 2 | 71 | 71 |
| olist_products | 9 | 32951 | 32951 |
| olist_sellers | 4 | 3095 | 3095 |

- Verified tables: **9**
- Total expected rows: **1550922**
- Total Athena rows: **1550922**
- Preserved multiline records: **3852**
- Row-count query ID: `a0cc757a-2924-4893-a40e-8e618eb0f963`
- Multiline query ID: `aa85f57e-8d82-4146-8ce1-a6642188050e`
- Row-count bytes scanned: **314973183**
- Multiline bytes scanned: **28915600**
- Total validation bytes scanned: **343888783**
- Athena engine: `Athena engine version 3`

## Result

All nine Terraform-managed Glue tables match the deterministic manifest. Athena returned the exact expected row count for every table, and all 3,852 source records containing embedded line breaks remained queryable.
