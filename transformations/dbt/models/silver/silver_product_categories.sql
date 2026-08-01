{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('product_category_name') }}
            as product_category_name,

        {{ clean_string('product_category_name_english') }}
            as product_category_name_english

    from {{
        source(
            'bronze',
            'olist_product_category_name_translation'
        )
    }}

),

deduplicated as (

    select distinct
        product_category_name,
        product_category_name_english

    from cleaned_source

)

select
    lower(product_category_name)
        as product_category_name,

    lower(product_category_name_english)
        as product_category_name_english

from deduplicated
