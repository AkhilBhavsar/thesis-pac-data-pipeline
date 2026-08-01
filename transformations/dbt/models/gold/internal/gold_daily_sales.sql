{{ config(
    external_location=zone_external_location(
        'gold/internal',
        'gold_daily_sales'
    )
) }}

select
    order_date,

    count(distinct order_id)
        as total_orders,

    count(distinct customer_unique_id)
        as unique_customers,

    sum(total_items)
        as units_sold,

    round(
        sum(product_revenue),
        2
    ) as product_revenue,

    round(
        sum(freight_revenue),
        2
    ) as freight_revenue,

    round(
        sum(total_revenue),
        2
    ) as total_revenue,

    round(
        coalesce(
            sum(total_revenue)
            / nullif(
                count(distinct order_id),
                0
            ),
            0
        ),
        2
    ) as average_order_value,

    round(
        coalesce(
            sum(freight_revenue)
            / nullif(
                count(distinct order_id),
                0
            ),
            0
        ),
        2
    ) as average_freight_value

from {{ ref('int_gold_order_financials') }}

group by order_date
