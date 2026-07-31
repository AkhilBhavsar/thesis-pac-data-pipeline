with duplicate_order_items as (

    select
        'silver_order_items' as dataset_name,
        concat(
            cast(order_id as varchar),
            '|',
            cast(order_item_id as varchar)
        ) as duplicate_key,
        count(*) as duplicate_count

    from {{ ref('silver_order_items') }}

    group by
        order_id,
        order_item_id

    having count(*) > 1

),

duplicate_payments as (

    select
        'silver_payments' as dataset_name,
        concat(
            cast(order_id as varchar),
            '|',
            cast(payment_sequential as varchar)
        ) as duplicate_key,
        count(*) as duplicate_count

    from {{ ref('silver_payments') }}

    group by
        order_id,
        payment_sequential

    having count(*) > 1

)

select *
from duplicate_order_items

union all

select *
from duplicate_payments
