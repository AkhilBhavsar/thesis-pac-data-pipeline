{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('customer_id') }}
            as customer_id,
        {{ clean_string('synthetic_email') }}
            as synthetic_email,
        {{ clean_string('synthetic_phone') }}
            as synthetic_phone,
        try_cast(marketing_consent as boolean)
            as marketing_consent,
        {{ clean_string('pii_classification') }}
            as pii_classification

    from {{ source('bronze', 'synthetic_customer_contact') }}

),

deduplicated as (

    select distinct
        customer_id,
        synthetic_email,
        synthetic_phone,
        marketing_consent,
        pii_classification

    from cleaned_source

)

select
    customer_id,
    lower(synthetic_email) as synthetic_email,
    synthetic_phone,
    marketing_consent,
    pii_classification

from deduplicated
