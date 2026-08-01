{{ config(
    external_location=zone_external_location(
        'gold/internal',
        'gold_customer_order_summary'
    )
) }}

with state_counts as (

    select
        customer_unique_id,
        customer_state,
        count(*) as state_frequency

    from {{ ref('int_gold_item_enriched') }}

    group by
        customer_unique_id,
        customer_state

),

ranked_states as (

    select
        customer_unique_id,
        customer_state,

        row_number() over (
            partition by customer_unique_id
            order by
                state_frequency desc,
                customer_state asc
        ) as state_rank

    from state_counts

),

customer_totals as (

    select
        customer_unique_id,

        min(order_date)
            as first_order_date,

        max(order_date)
            as latest_order_date,

        count(distinct order_id)
            as total_orders,

        count(order_item_id)
            as total_items,

        count(distinct product_id)
            as distinct_products,

        sum(price)
            as product_revenue_raw,

        sum(freight_value)
            as freight_revenue_raw,

        sum(item_total_value)
            as total_spend_raw

    from {{ ref('int_gold_item_enriched') }}

    group by customer_unique_id

)

select
    totals.customer_unique_id,

    coalesce(
        states.customer_state,
        'UNKNOWN'
    ) as customer_state,

    totals.first_order_date,
    totals.latest_order_date,
    totals.total_orders,
    totals.total_items,
    totals.distinct_products,

    round(
        totals.product_revenue_raw,
        2
    ) as product_revenue,

    round(
        totals.freight_revenue_raw,
        2
    ) as freight_revenue,

    round(
        totals.total_spend_raw,
        2
    ) as total_spend,

    round(
        coalesce(
            totals.total_spend_raw
            / nullif(
                totals.total_orders,
                0
            ),
            0
        ),
        2
    ) as average_order_value

from customer_totals as totals

left join ranked_states as states
    on totals.customer_unique_id
        = states.customer_unique_id
    and states.state_rank = 1
