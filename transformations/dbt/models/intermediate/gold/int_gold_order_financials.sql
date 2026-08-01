select
    order_id,
    customer_id,
    customer_unique_id,
    customer_state,
    order_date,

    count(order_item_id)
        as total_items,

    count(distinct product_id)
        as distinct_products,

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
    order_id,
    customer_id,
    customer_unique_id,
    customer_state,
    order_date
