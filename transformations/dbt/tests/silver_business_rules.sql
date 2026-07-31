with failures as (

    select
        'silver_order_items_price_non_negative'
            as check_name,
        cast(order_id as varchar) as record_key

    from {{ ref('silver_order_items') }}

    where price is null
        or price < 0

    union all

    select
        'silver_order_items_freight_non_negative'
            as check_name,
        cast(order_id as varchar) as record_key

    from {{ ref('silver_order_items') }}

    where freight_value is null
        or freight_value < 0

    union all

    select
        'silver_order_items_total_reconciles'
            as check_name,
        cast(order_id as varchar) as record_key

    from {{ ref('silver_order_items') }}

    where item_total_value is null
        or abs(
            item_total_value
            - (price + freight_value)
        ) > 0.000001

    union all

    select
        'silver_reviews_score_between_1_and_5'
            as check_name,
        review_record_id as record_key

    from {{ ref('silver_reviews') }}

    where review_score is null
        or review_score not between 1 and 5

    union all

    select
        'silver_geolocation_latitude_valid'
            as check_name,
        cast(
            geolocation_zip_code_prefix
            as varchar
        ) as record_key

    from {{ ref('silver_geolocation') }}

    where geolocation_lat is null
        or geolocation_lat not between -90 and 90

    union all

    select
        'silver_geolocation_longitude_valid'
            as check_name,
        cast(
            geolocation_zip_code_prefix
            as varchar
        ) as record_key

    from {{ ref('silver_geolocation') }}

    where geolocation_lng is null
        or geolocation_lng not between -180 and 180

    union all

    select
        'silver_customer_contact_consent_valid'
            as check_name,
        customer_id as record_key

    from {{ ref('silver_customer_contact') }}

    where marketing_consent is null

)

select *
from failures
