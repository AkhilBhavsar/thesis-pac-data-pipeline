SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT customer_id) AS distinct_customer_ids,
    COUNT(DISTINCT synthetic_email) AS distinct_synthetic_emails,
    COUNT(DISTINCT synthetic_phone) AS distinct_synthetic_phones,

    SUM(
        CASE
            WHEN marketing_consent THEN 1
            ELSE 0
        END
    ) AS consent_true_rows,

    SUM(
        CASE
            WHEN NOT marketing_consent THEN 1
            ELSE 0
        END
    ) AS consent_false_rows,

    SUM(
        CASE
            WHEN marketing_consent IS NULL THEN 1
            ELSE 0
        END
    ) AS null_consent_rows,

    SUM(
        CASE
            WHEN pii_classification = 'PII' THEN 1
            ELSE 0
        END
    ) AS pii_rows,

    SUM(
        CASE
            WHEN pii_classification <> 'PII'
                 OR pii_classification IS NULL
            THEN 1
            ELSE 0
        END
    ) AS non_pii_or_null_rows,

    SUM(
        CASE
            WHEN customer_id IS NULL THEN 1
            ELSE 0
        END
    ) AS null_customer_ids,

    SUM(
        CASE
            WHEN synthetic_email IS NULL THEN 1
            ELSE 0
        END
    ) AS null_synthetic_emails,

    SUM(
        CASE
            WHEN synthetic_phone IS NULL THEN 1
            ELSE 0
        END
    ) AS null_synthetic_phones

FROM synthetic_customer_contact
