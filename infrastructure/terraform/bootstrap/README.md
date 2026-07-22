# Terraform Bootstrap

This configuration creates the protected Amazon S3 bucket used for
remote Terraform state.

The bootstrap configuration intentionally uses local Terraform state.
After the state bucket is created, the development environment will use
the S3 backend with native lockfile-based state locking.

## Security controls

- S3 Block Public Access enabled
- bucket-owner-enforced object ownership
- S3 versioning enabled
- server-side encryption enabled
- insecure HTTP transport denied
- noncurrent state versions retained
- accidental Terraform destruction prevented
- incomplete multipart uploads removed after seven days

## Initialise and validate

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
