select
    order_date,
    customer_state,
    product_category_name_english,
    count(*) as duplicate_count

from {{ ref('gold_public_sales_dashboard') }}

group by
    order_date,
    customer_state,
    product_category_name_english

having count(*) > 1
