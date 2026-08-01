# Supporting Bronze Deployment Verification

- Overall status: PASS
- Terraform apply: 1 added, 0 changed, 0 destroyed
- Post-apply Terraform drift: 0 changes
- Governed Bronze Glue tables: 10
- Supporting table: `synthetic_customer_contact`
- Generated snapshot ID: `1b7972218afd4016928dfb185f7eff30dd2a612384b357beae24bf8daac44e2c`
- Approved Terraform plan SHA-256: `d195a795a98f2114695727b6a9b1dbe75b4de2e034a8e0c83d64edcf02f25048`

## Athena verification

- Total rows: 99441
- Distinct customer IDs: 99441
- Distinct synthetic emails: 99441
- Distinct synthetic phones: 99441
- Consent true rows: 74553
- Consent false rows: 24888
- Null consent rows: 0
- PII-classified rows: 99441
- Non-PII or null classification rows: 0
- Athena data scanned: 20509734 bytes

## Governance

- Contains real PII: false
- Contains simulated PII: true
