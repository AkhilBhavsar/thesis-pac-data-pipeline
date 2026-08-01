with failures as (

    select
        'gold_daily_sales' as dataset_name,
        count(*) as actual_rows,
        cast(612 as bigint) as expected_rows

    from {{ ref('gold_daily_sales') }}

    having count(*) <> 612

    union all

    select
        'gold_sales_by_state',
        count(*),
        cast(27 as bigint)

    from {{ ref('gold_sales_by_state') }}

    having count(*) <> 27

    union all

    select
        'gold_product_category_revenue',
        count(*),
        cast(72 as bigint)

    from {{ ref('gold_product_category_revenue') }}

    having count(*) <> 72

    union all

    select
        'gold_customer_order_summary',
        count(*),
        cast(93358 as bigint)

    from {{ ref('gold_customer_order_summary') }}

    having count(*) <> 93358

    union all

    select
        'gold_public_sales_dashboard',
        count(*),
        cast(55872 as bigint)

    from {{ ref('gold_public_sales_dashboard') }}

    having count(*) <> 55872

)

select *
from failures
