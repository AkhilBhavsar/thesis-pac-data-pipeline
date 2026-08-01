with failures as (

    select
        'gold_daily_sales_revenue'
            as check_name,

        cast(order_date as varchar)
            as record_key

    from {{ ref('gold_daily_sales') }}

    where abs(
        product_revenue
        + freight_revenue
        - total_revenue
    ) > 0.02

    union all

    select
        'gold_daily_sales_average_order_value',
        cast(order_date as varchar)

    from {{ ref('gold_daily_sales') }}

    where abs(
        average_order_value
        - coalesce(
            total_revenue
            / nullif(total_orders, 0),
            0
        )
    ) > 0.02

    union all

    select
        'gold_daily_sales_average_freight_value',
        cast(order_date as varchar)

    from {{ ref('gold_daily_sales') }}

    where abs(
        average_freight_value
        - coalesce(
            freight_revenue
            / nullif(total_orders, 0),
            0
        )
    ) > 0.02

    union all

    select
        'gold_sales_by_state_revenue',
        customer_state

    from {{ ref('gold_sales_by_state') }}

    where abs(
        product_revenue
        + freight_revenue
        - total_revenue
    ) > 0.02

    union all

    select
        'gold_sales_by_state_average_order_value',
        customer_state

    from {{ ref('gold_sales_by_state') }}

    where abs(
        average_order_value
        - coalesce(
            total_revenue
            / nullif(total_orders, 0),
            0
        )
    ) > 0.02

    union all

    select
        'gold_product_category_revenue_components',
        product_category_name_english

    from {{ ref('gold_product_category_revenue') }}

    where abs(
        product_revenue
        + freight_revenue
        - total_revenue
    ) > 0.02

    union all

    select
        'gold_product_category_average_item_price',
        product_category_name_english

    from {{ ref('gold_product_category_revenue') }}

    where abs(
        average_item_price
        - coalesce(
            product_revenue
            / nullif(units_sold, 0),
            0
        )
    ) > 0.02

    union all

    select
        'gold_customer_order_summary_revenue',
        customer_unique_id

    from {{ ref('gold_customer_order_summary') }}

    where abs(
        product_revenue
        + freight_revenue
        - total_spend
    ) > 0.02

    union all

    select
        'gold_customer_order_summary_average_order_value',
        customer_unique_id

    from {{ ref('gold_customer_order_summary') }}

    where abs(
        average_order_value
        - coalesce(
            total_spend
            / nullif(total_orders, 0),
            0
        )
    ) > 0.02

    union all

    select
        'gold_public_sales_dashboard_revenue',

        concat(
            cast(order_date as varchar),
            '|',
            customer_state,
            '|',
            product_category_name_english
        )

    from {{ ref('gold_public_sales_dashboard') }}

    where abs(
        product_revenue
        + freight_revenue
        - total_revenue
    ) > 0.02

)

select *
from failures
