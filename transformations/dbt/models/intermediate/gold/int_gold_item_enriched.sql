with delivered_orders as (

    select
        order_id,
        customer_id,
        cast(order_purchase_timestamp as date)
            as order_date

    from {{ ref('silver_orders') }}

    where lower(order_status) = 'delivered'
        and order_purchase_timestamp is not null

),

normalised_customers as (

    select
        customer_id,
        customer_unique_id,

        coalesce(
            upper(customer_state),
            'UNKNOWN'
        ) as customer_state

    from {{ ref('silver_customers') }}

),

normalised_products as (

    select
        product_id,

        lower(product_category_name)
            as product_category_name

    from {{ ref('silver_products') }}

),

normalised_categories as (

    select
        lower(product_category_name)
            as product_category_name,

        lower(product_category_name_english)
            as product_category_name_english

    from {{ ref('silver_product_categories') }}

)

select
    items.order_id,
    items.order_item_id,
    items.product_id,
    items.seller_id,
    delivered.customer_id,
    customers.customer_unique_id,

    coalesce(
        customers.customer_state,
        'UNKNOWN'
    ) as customer_state,

    delivered.order_date,

    coalesce(
        categories.product_category_name_english,
        'unknown'
    ) as product_category_name_english,

    coalesce(
        items.price,
        0.0
    ) as price,

    coalesce(
        items.freight_value,
        0.0
    ) as freight_value,

    coalesce(
        items.item_total_value,
        0.0
    ) as item_total_value

from {{ ref('silver_order_items') }} as items

inner join delivered_orders as delivered
    on items.order_id = delivered.order_id

left join normalised_customers as customers
    on delivered.customer_id = customers.customer_id

left join normalised_products as products
    on items.product_id = products.product_id

left join normalised_categories as categories
    on products.product_category_name
        = categories.product_category_name
