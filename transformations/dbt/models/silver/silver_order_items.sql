{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('order_id') }}
            as order_id,

        try_cast(
            {{ clean_string('order_item_id') }}
            as bigint
        ) as order_item_id,

        {{ clean_string('product_id') }}
            as product_id,

        {{ clean_string('seller_id') }}
            as seller_id,

        {{ parse_timestamp('shipping_limit_date') }}
            as shipping_limit_date,

        try_cast(
            {{ clean_string('price') }}
            as double
        ) as price,

        try_cast(
            {{ clean_string('freight_value') }}
            as double
        ) as freight_value

    from {{ source('bronze', 'olist_order_items') }}

),

deduplicated as (

    select distinct
        order_id,
        order_item_id,
        product_id,
        seller_id,
        shipping_limit_date,
        price,
        freight_value

    from cleaned_source

)

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value,
    price + freight_value as item_total_value

from deduplicated
