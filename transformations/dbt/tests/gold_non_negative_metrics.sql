with failures as (

    select
        'gold_daily_sales'
            as dataset_name,

        cast(order_date as varchar)
            as record_key

    from {{ ref('gold_daily_sales') }}

    where total_orders < 0
        or unique_customers < 0
        or units_sold < 0
        or product_revenue < 0
        or freight_revenue < 0
        or total_revenue < 0
        or average_order_value < 0
        or average_freight_value < 0

    union all

    select
        'gold_sales_by_state',
        customer_state

    from {{ ref('gold_sales_by_state') }}

    where total_orders < 0
        or unique_customers < 0
        or units_sold < 0
        or product_revenue < 0
        or freight_revenue < 0
        or total_revenue < 0
        or average_order_value < 0

    union all

    select
        'gold_product_category_revenue',
        product_category_name_english

    from {{ ref('gold_product_category_revenue') }}

    where total_orders < 0
        or unique_customers < 0
        or units_sold < 0
        or product_revenue < 0
        or freight_revenue < 0
        or total_revenue < 0
        or average_item_price < 0
        or revenue_share_pct < 0
        or revenue_share_pct > 100

    union all

    select
        'gold_customer_order_summary',
        customer_unique_id

    from {{ ref('gold_customer_order_summary') }}

    where total_orders < 0
        or total_items < 0
        or distinct_products < 0
        or product_revenue < 0
        or freight_revenue < 0
        or total_spend < 0
        or average_order_value < 0

    union all

    select
        'gold_public_sales_dashboard',

        concat(
            cast(order_date as varchar),
            '|',
            customer_state,
            '|',
            product_category_name_english
        )

    from {{ ref('gold_public_sales_dashboard') }}

    where total_orders < 0
        or units_sold < 0
        or product_revenue < 0
        or freight_revenue < 0
        or total_revenue < 0

)

select *
from failures
