with failures as (

    select
        'silver_orders_customer_id'
            as relationship_name,
        orders.customer_id as orphan_key

    from {{ ref('silver_orders') }} as orders

    left join {{ ref('silver_customers') }} as customers
        on orders.customer_id = customers.customer_id

    where customers.customer_id is null

    union all

    select
        'silver_order_items_order_id'
            as relationship_name,
        items.order_id as orphan_key

    from {{ ref('silver_order_items') }} as items

    left join {{ ref('silver_orders') }} as orders
        on items.order_id = orders.order_id

    where orders.order_id is null

    union all

    select
        'silver_order_items_product_id'
            as relationship_name,
        items.product_id as orphan_key

    from {{ ref('silver_order_items') }} as items

    left join {{ ref('silver_products') }} as products
        on items.product_id = products.product_id

    where products.product_id is null

    union all

    select
        'silver_order_items_seller_id'
            as relationship_name,
        items.seller_id as orphan_key

    from {{ ref('silver_order_items') }} as items

    left join {{ ref('silver_sellers') }} as sellers
        on items.seller_id = sellers.seller_id

    where sellers.seller_id is null

    union all

    select
        'silver_payments_order_id'
            as relationship_name,
        payments.order_id as orphan_key

    from {{ ref('silver_payments') }} as payments

    left join {{ ref('silver_orders') }} as orders
        on payments.order_id = orders.order_id

    where orders.order_id is null

    union all

    select
        'silver_customer_contact_customer_id'
            as relationship_name,
        contact.customer_id as orphan_key

    from {{ ref('silver_customer_contact') }} as contact

    left join {{ ref('silver_customers') }} as customers
        on contact.customer_id = customers.customer_id

    where customers.customer_id is null

    union all

    select
        'silver_reviews_order_id'
            as relationship_name,
        reviews.order_id as orphan_key

    from {{ ref('silver_reviews') }} as reviews

    left join {{ ref('silver_orders') }} as orders
        on reviews.order_id = orders.order_id

    where orders.order_id is null

)

select *
from failures
