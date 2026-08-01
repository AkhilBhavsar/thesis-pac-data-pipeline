{{ config(
    external_location=zone_external_location(
        'gold/public',
        'gold_public_sales_dashboard'
    )
) }}

select
    order_date,
    customer_state,
    product_category_name_english,

    count(distinct order_id)
        as total_orders,

    count(order_item_id)
        as units_sold,

    round(
        sum(price),
        2
    ) as product_revenue,

    round(
        sum(freight_value),
        2
    ) as freight_revenue,

    round(
        sum(item_total_value),
        2
    ) as total_revenue

from {{ ref('int_gold_item_enriched') }}

group by
    order_date,
    customer_state,
    product_category_name_english
