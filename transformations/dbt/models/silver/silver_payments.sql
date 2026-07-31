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
            {{ clean_string('payment_sequential') }}
            as bigint
        ) as payment_sequential,

        {{ clean_string('payment_type') }}
            as payment_type,

        try_cast(
            {{ clean_string('payment_installments') }}
            as bigint
        ) as payment_installments,

        try_cast(
            {{ clean_string('payment_value') }}
            as double
        ) as payment_value

    from {{ source('bronze', 'olist_order_payments') }}

),

deduplicated as (

    select distinct
        order_id,
        payment_sequential,
        payment_type,
        payment_installments,
        payment_value

    from cleaned_source

)

select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value

from deduplicated
