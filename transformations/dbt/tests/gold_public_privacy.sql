{{ config(tags=['gold']) }}

{% set gold_public_schema = env_var(
    'DBT_GOLD_PUBLIC_SCHEMA',
    'thesis_pac_dev_gold_public'
) | trim %}

select
    column_name

from information_schema.columns

where table_schema = '{{ gold_public_schema }}'
    and table_name = 'gold_public_sales_dashboard'
    and (
        lower(column_name) in (
            'customer_id',
            'customer_unique_id',
            'order_id',
            'product_id',
            'seller_id',
            'review_id',
            'synthetic_email',
            'synthetic_phone',
            'marketing_consent',
            'customer_zip_code_prefix',
            'seller_zip_code_prefix',
            'address'
        )

        or regexp_like(
            lower(column_name),
            'email|phone|address|zip_code|postal|consent'
        )
    )
