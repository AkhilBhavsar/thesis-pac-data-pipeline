{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('seller_id') }}
            as seller_id,

        try_cast(
            {{ clean_string('seller_zip_code_prefix') }}
            as bigint
        ) as seller_zip_code_prefix,

        {{ clean_string('seller_city') }}
            as seller_city,

        {{ clean_string('seller_state') }}
            as seller_state

    from {{ source('bronze', 'olist_sellers') }}

),

deduplicated as (

    select distinct
        seller_id,
        seller_zip_code_prefix,
        seller_city,
        seller_state

    from cleaned_source

)

select
    seller_id,
    seller_zip_code_prefix,
    lower(seller_city) as seller_city,
    upper(seller_state) as seller_state

from deduplicated
