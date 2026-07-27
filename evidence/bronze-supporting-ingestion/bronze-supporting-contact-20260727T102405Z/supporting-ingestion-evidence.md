# Synthetic Customer-Contact Bronze Ingestion Evidence

- Overall status: **PASS**
- Run ID: `bronze-supporting-contact-20260727T102405Z`
- AWS account: `522814714524`
- AWS region: `eu-west-1`
- S3 bucket: `thesis-pac-dev-data-lake-522814714524-eu-west-1`
- Source system: `olist-derived-synthetic-supporting`
- Dataset class: `generated_supporting_data`
- Source snapshot: `43cc5e9c8436f7919491dd90872d6f4d94d61d4694c1d4307e41456e405052d2`
- Generated snapshot: `1b7972218afd4016928dfb185f7eff30dd2a612384b357beae24bf8daac44e2c`
- Representation: `athena-json-lines`
- Dataset rows: **99441**
- Dataset and source bytes: **30976008**
- Verified S3 objects: **3**
- Contains real PII: **False**
- Contains simulated PII: **True**

## Action counts

- `uploaded`: **3**

## Objects

| Object | Kind | Action | Bytes | Version ID | SHA-256 |
|---|---|---:|---:|---|---|
| `bronze/generated/supporting/synthetic-customer-contact/snapshots/1b7972218afd4016928dfb185f7eff30dd2a612384b357beae24bf8daac44e2c/source/synthetic_customer_contact.csv` | `supporting-source-csv` | uploaded | 10466274 | `H5UY4j2N7QbARO5tpH9tBeJ0mz9EbYGs` | `06f3d4d7fe3511e90e511abbb2c04a72d01309009a8c3cf239a116a7781cac65` |
| `bronze/generated/supporting/synthetic-customer-contact/snapshots/1b7972218afd4016928dfb185f7eff30dd2a612384b357beae24bf8daac44e2c/tables/synthetic_customer_contact/data.jsonl` | `supporting-dataset` | uploaded | 20509734 | `j7ws539TAS5.V7b.ALuNj..9mdaqDRRZ` | `9585db5f832eafdfff201262037de50cf2713bdb5b7f83366ddc150988e535c4` |
| `bronze/generated/supporting/synthetic-customer-contact/snapshots/1b7972218afd4016928dfb185f7eff30dd2a612384b357beae24bf8daac44e2c/synthetic-customer-contact-manifest.json` | `supporting-manifest` | uploaded | 4971 | `i4h_LfCLoTMl8iIhLLagGqBwe32FAqlW` | `0bd76ea319996dc2b6661fe1018e403380bf2dde71339e916c2bbf6242fd1539` |
