{{ config(tags=['gold']) }}

-- depends_on: {{ ref('gold_daily_sales') }}
-- depends_on: {{ ref('gold_sales_by_state') }}
-- depends_on: {{ ref('gold_product_category_revenue') }}
-- depends_on: {{ ref('gold_customer_order_summary') }}
-- depends_on: {{ ref('gold_public_sales_dashboard') }}

{% set gold_internal_schema = env_var(
    'DBT_GOLD_INTERNAL_SCHEMA',
    'thesis_pac_dev_gold_internal'
) | trim %}

{% set gold_public_schema = env_var(
    'DBT_GOLD_PUBLIC_SCHEMA',
    'thesis_pac_dev_gold_public'
) | trim %}

with expected (
    table_schema,
    table_name,
    ordinal_position,
    column_name
) as (

    values
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 1, 'order_date'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 2, 'total_orders'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 3, 'unique_customers'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 4, 'units_sold'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 5, 'product_revenue'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 6, 'freight_revenue'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 7, 'total_revenue'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 8, 'average_order_value'),
        ('{{ gold_internal_schema }}', 'gold_daily_sales', 9, 'average_freight_value'),

        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 1, 'customer_state'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 2, 'total_orders'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 3, 'unique_customers'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 4, 'units_sold'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 5, 'product_revenue'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 6, 'freight_revenue'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 7, 'total_revenue'),
        ('{{ gold_internal_schema }}', 'gold_sales_by_state', 8, 'average_order_value'),

        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 1, 'product_category_name_english'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 2, 'total_orders'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 3, 'unique_customers'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 4, 'units_sold'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 5, 'product_revenue'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 6, 'freight_revenue'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 7, 'total_revenue'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 8, 'average_item_price'),
        ('{{ gold_internal_schema }}', 'gold_product_category_revenue', 9, 'revenue_share_pct'),

        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 1, 'customer_unique_id'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 2, 'customer_state'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 3, 'first_order_date'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 4, 'latest_order_date'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 5, 'total_orders'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 6, 'total_items'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 7, 'distinct_products'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 8, 'product_revenue'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 9, 'freight_revenue'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 10, 'total_spend'),
        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 11, 'average_order_value'),

        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 1, 'order_date'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 2, 'customer_state'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 3, 'product_category_name_english'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 4, 'total_orders'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 5, 'units_sold'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 6, 'product_revenue'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 7, 'freight_revenue'),
        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 8, 'total_revenue')

),

actual as (

    select
        table_schema,
        table_name,
        ordinal_position,
        column_name

    from information_schema.columns

    where table_schema in (
        '{{ gold_internal_schema }}',
        '{{ gold_public_schema }}'
    )

    and table_name in (
        'gold_daily_sales',
        'gold_sales_by_state',
        'gold_product_category_revenue',
        'gold_customer_order_summary',
        'gold_public_sales_dashboard'
    )

),

missing_or_misordered as (

    select
        'missing_or_misordered'
            as issue_type,

        expected.table_schema,
        expected.table_name,
        expected.ordinal_position,
        expected.column_name

    from expected

    left join actual
        on expected.table_schema
            = actual.table_schema

        and expected.table_name
            = actual.table_name

        and expected.ordinal_position
            = actual.ordinal_position

        and expected.column_name
            = actual.column_name

    where actual.column_name is null

),

unexpected_or_misordered as (

    select
        'unexpected_or_misordered'
            as issue_type,

        actual.table_schema,
        actual.table_name,
        actual.ordinal_position,
        actual.column_name

    from actual

    left join expected
        on actual.table_schema
            = expected.table_schema

        and actual.table_name
            = expected.table_name

        and actual.ordinal_position
            = expected.ordinal_position

        and actual.column_name
            = expected.column_name

    where expected.column_name is null

)

select *
from missing_or_misordered

union all

select *
from unexpected_or_misordered
