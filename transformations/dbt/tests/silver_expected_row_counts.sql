with row_count_failures as (

    select
        'silver_customer_contact' as dataset_name,
        count(*) as actual_rows,
        cast(99441 as bigint) as expected_rows

    from {{ ref('silver_customer_contact') }}

    having count(*) <> 99441

    union all

    select
        'silver_customers',
        count(*),
        cast(99441 as bigint)

    from {{ ref('silver_customers') }}

    having count(*) <> 99441

    union all

    select
        'silver_geolocation',
        count(*),
        cast(19015 as bigint)

    from {{ ref('silver_geolocation') }}

    having count(*) <> 19015

    union all

    select
        'silver_order_items',
        count(*),
        cast(112650 as bigint)

    from {{ ref('silver_order_items') }}

    having count(*) <> 112650

    union all

    select
        'silver_orders',
        count(*),
        cast(99441 as bigint)

    from {{ ref('silver_orders') }}

    having count(*) <> 99441

    union all

    select
        'silver_payments',
        count(*),
        cast(103886 as bigint)

    from {{ ref('silver_payments') }}

    having count(*) <> 103886

    union all

    select
        'silver_product_categories',
        count(*),
        cast(71 as bigint)

    from {{ ref('silver_product_categories') }}

    having count(*) <> 71

    union all

    select
        'silver_products',
        count(*),
        cast(32951 as bigint)

    from {{ ref('silver_products') }}

    having count(*) <> 32951

    union all

    select
        'silver_reviews',
        count(*),
        cast(99224 as bigint)

    from {{ ref('silver_reviews') }}

    having count(*) <> 99224

    union all

    select
        'silver_sellers',
        count(*),
        cast(3095 as bigint)

    from {{ ref('silver_sellers') }}

    having count(*) <> 3095

)

select *
from row_count_failures
