{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        {{ clean_string('review_id') }}
            as review_id,

        {{ clean_string('order_id') }}
            as order_id,

        try_cast(
            {{ clean_string('review_score') }}
            as bigint
        ) as review_score,

        {{ clean_string('review_comment_title') }}
            as review_comment_title,

        {{ clean_string('review_comment_message') }}
            as review_comment_message,

        {{ parse_timestamp('review_creation_date') }}
            as review_creation_date,

        {{ parse_timestamp('review_answer_timestamp') }}
            as review_answer_timestamp

    from {{ source('bronze', 'olist_order_reviews') }}

),

deduplicated as (

    select distinct
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp

    from cleaned_source

),

numbered as (

    select
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp,

        row_number() over (
            partition by
                review_id,
                order_id,
                review_creation_date,
                review_answer_timestamp

            order by
                coalesce(review_comment_title, ''),
                coalesce(review_comment_message, ''),
                coalesce(review_score, -1)
        ) as review_occurrence

    from deduplicated

),

identified as (

    select
        to_hex(
            sha256(
                to_utf8(
                    concat(
                        coalesce(review_id, ''),
                        '|',
                        coalesce(order_id, ''),
                        '|',
                        case
                            when review_creation_date is null
                                then ''
                            else concat(
                                format_datetime(
                                    review_creation_date,
                                    'yyyy-MM-dd HH:mm:ss'
                                ),
                                '+00:00'
                            )
                        end,
                        '|',
                        case
                            when review_answer_timestamp is null
                                then ''
                            else concat(
                                format_datetime(
                                    review_answer_timestamp,
                                    'yyyy-MM-dd HH:mm:ss'
                                ),
                                '+00:00'
                            )
                        end,
                        '|',
                        cast(review_occurrence as varchar)
                    )
                )
            )
        ) as review_record_id,

        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp,
        review_occurrence

    from numbered

)

select
    review_record_id,
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp,
    review_occurrence

from identified
