{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('product_id') }}
            as product_id,

        {{ clean_string('product_category_name') }}
            as product_category_name,

        try_cast(
            {{ clean_string('product_name_lenght') }}
            as double
        ) as product_name_length,

        try_cast(
            {{ clean_string('product_description_lenght') }}
            as double
        ) as product_description_length,

        try_cast(
            {{ clean_string('product_photos_qty') }}
            as double
        ) as product_photos_qty,

        try_cast(
            {{ clean_string('product_weight_g') }}
            as double
        ) as product_weight_g,

        try_cast(
            {{ clean_string('product_length_cm') }}
            as double
        ) as product_length_cm,

        try_cast(
            {{ clean_string('product_height_cm') }}
            as double
        ) as product_height_cm,

        try_cast(
            {{ clean_string('product_width_cm') }}
            as double
        ) as product_width_cm

    from {{ source('bronze', 'olist_products') }}

),

deduplicated as (

    select distinct
        product_id,
        product_category_name,
        product_name_length,
        product_description_length,
        product_photos_qty,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm

    from cleaned_source

)

select
    product_id,
    product_category_name,
    product_name_length,
    product_description_length,
    product_photos_qty,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm

from deduplicated
