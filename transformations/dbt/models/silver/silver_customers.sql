{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('customer_id') }}
            as customer_id,
        {{ clean_string('customer_unique_id') }}
            as customer_unique_id,
        try_cast(
            {{ clean_string('customer_zip_code_prefix') }}
            as bigint
        ) as customer_zip_code_prefix,
        {{ clean_string('customer_city') }}
            as customer_city,
        {{ clean_string('customer_state') }}
            as customer_state

    from {{ source('bronze', 'olist_customers') }}

),

deduplicated as (

    select distinct
        customer_id,
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state

    from cleaned_source

)

select
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    lower(customer_city) as customer_city,
    upper(customer_state) as customer_state

from deduplicated
