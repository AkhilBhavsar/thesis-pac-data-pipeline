{{ config(
    external_location=zone_external_location(
        'gold/internal',
        'gold_product_category_revenue'
    )
) }}

with category_totals as (

    select
        product_category_name_english,

        count(distinct order_id)
            as total_orders,

        count(distinct customer_unique_id)
            as unique_customers,

        count(order_item_id)
            as units_sold,

        sum(price)
            as product_revenue_raw,

        sum(freight_value)
            as freight_revenue_raw,

        sum(item_total_value)
            as total_revenue_raw,

        avg(price)
            as average_item_price_raw

    from {{ ref('int_gold_item_enriched') }}

    group by product_category_name_english

)

select
    product_category_name_english,
    total_orders,
    unique_customers,
    units_sold,

    round(
        product_revenue_raw,
        2
    ) as product_revenue,

    round(
        freight_revenue_raw,
        2
    ) as freight_revenue,

    round(
        total_revenue_raw,
        2
    ) as total_revenue,

    round(
        average_item_price_raw,
        2
    ) as average_item_price,

    round(
        coalesce(
            total_revenue_raw
            * 100.0
            / nullif(
                sum(total_revenue_raw) over (),
                0
            ),
            0
        ),
        2
    ) as revenue_share_pct

from category_totals
