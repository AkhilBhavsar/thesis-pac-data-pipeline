{{
    config(
        materialized='table',
        table_type='hive',
        format='parquet',
        tags=['silver', 'reference_parity']
    )
}}

with cleaned_source as (

    select
        {{ clean_string('order_id') }}
            as order_id,
        {{ clean_string('customer_id') }}
            as customer_id,
        {{ clean_string('order_status') }}
            as order_status,
        {{ clean_string('order_purchase_timestamp') }}
            as order_purchase_timestamp,
        {{ clean_string('order_approved_at') }}
            as order_approved_at,
        {{ clean_string('order_delivered_carrier_date') }}
            as order_delivered_carrier_date,
        {{ clean_string('order_delivered_customer_date') }}
            as order_delivered_customer_date,
        {{ clean_string('order_estimated_delivery_date') }}
            as order_estimated_delivery_date

    from {{ source('bronze', 'olist_orders') }}

),

typed_source as (

    select
        order_id,
        customer_id,
        order_status,

        {{ parse_timestamp('order_purchase_timestamp') }}
            as order_purchase_timestamp,

        {{ parse_timestamp('order_approved_at') }}
            as order_approved_at,

        {{ parse_timestamp('order_delivered_carrier_date') }}
            as order_delivered_carrier_date,

        {{ parse_timestamp('order_delivered_customer_date') }}
            as order_delivered_customer_date,

        {{ parse_timestamp('order_estimated_delivery_date') }}
            as order_estimated_delivery_date

    from cleaned_source

),

deduplicated as (

    select distinct
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date

    from typed_source

)

select
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,

    cast(
        order_purchase_timestamp
        as date
    ) as order_purchase_date,

    {{ fractional_days_between(
        'order_estimated_delivery_date',
        'order_delivered_customer_date'
    ) }} as delivery_delay_days,

    {{ fractional_days_between(
        'order_purchase_timestamp',
        'order_delivered_customer_date'
    ) }} as actual_delivery_days

from deduplicated
