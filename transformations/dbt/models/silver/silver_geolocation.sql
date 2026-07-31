{{ config(
    materialized='table',
    table_type='hive',
    format='parquet'
) }}

with cleaned_source as (

    select
        try_cast(
            {{ clean_string('geolocation_zip_code_prefix') }}
            as bigint
        ) as geolocation_zip_code_prefix,

        try_cast(
            {{ clean_string('geolocation_lat') }}
            as double
        ) as geolocation_lat,

        try_cast(
            {{ clean_string('geolocation_lng') }}
            as double
        ) as geolocation_lng,

        {{ clean_string('geolocation_city') }}
            as geolocation_city,

        {{ clean_string('geolocation_state') }}
            as geolocation_state

    from {{ source('bronze', 'olist_geolocation') }}

),

deduplicated as (

    select distinct
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state

    from cleaned_source

),

normalised as (

    select
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        lower(geolocation_city)
            as geolocation_city,
        upper(geolocation_state)
            as geolocation_state

    from deduplicated

    where geolocation_zip_code_prefix is not null

),

coordinate_arrays as (

    select
        geolocation_zip_code_prefix,

        array_sort(
            filter(
                array_agg(geolocation_lat),
                value -> value is not null
            )
        ) as latitude_values,

        array_sort(
            filter(
                array_agg(geolocation_lng),
                value -> value is not null
            )
        ) as longitude_values,

        count(*) as source_location_records

    from normalised

    group by geolocation_zip_code_prefix

),

coordinate_medians as (

    select
        geolocation_zip_code_prefix,

        case
            when cardinality(latitude_values) = 0
                then cast(null as double)

            when mod(cardinality(latitude_values), 2) = 1
                then element_at(
                    latitude_values,
                    cast(
                        (
                            cardinality(latitude_values) + 1
                        ) / 2
                        as integer
                    )
                )

            else (
                element_at(
                    latitude_values,
                    cast(
                        cardinality(latitude_values) / 2
                        as integer
                    )
                )
                +
                element_at(
                    latitude_values,
                    cast(
                        cardinality(latitude_values) / 2 + 1
                        as integer
                    )
                )
            ) / 2.0
        end as geolocation_lat,

        case
            when cardinality(longitude_values) = 0
                then cast(null as double)

            when mod(cardinality(longitude_values), 2) = 1
                then element_at(
                    longitude_values,
                    cast(
                        (
                            cardinality(longitude_values) + 1
                        ) / 2
                        as integer
                    )
                )

            else (
                element_at(
                    longitude_values,
                    cast(
                        cardinality(longitude_values) / 2
                        as integer
                    )
                )
                +
                element_at(
                    longitude_values,
                    cast(
                        cardinality(longitude_values) / 2 + 1
                        as integer
                    )
                )
            ) / 2.0
        end as geolocation_lng,

        source_location_records

    from coordinate_arrays

),

city_counts as (

    select
        geolocation_zip_code_prefix,
        geolocation_city,
        count(*) as value_count

    from normalised

    where geolocation_city is not null

    group by
        geolocation_zip_code_prefix,
        geolocation_city

),

ranked_cities as (

    select
        geolocation_zip_code_prefix,
        geolocation_city,

        row_number() over (
            partition by geolocation_zip_code_prefix
            order by
                value_count desc,
                geolocation_city asc
        ) as value_rank

    from city_counts

),

state_counts as (

    select
        geolocation_zip_code_prefix,
        geolocation_state,
        count(*) as value_count

    from normalised

    where geolocation_state is not null

    group by
        geolocation_zip_code_prefix,
        geolocation_state

),

ranked_states as (

    select
        geolocation_zip_code_prefix,
        geolocation_state,

        row_number() over (
            partition by geolocation_zip_code_prefix
            order by
                value_count desc,
                geolocation_state asc
        ) as value_rank

    from state_counts

)

select
    coordinates.geolocation_zip_code_prefix,

    round(
        coordinates.geolocation_lat,
        10
    ) as geolocation_lat,

    round(
        coordinates.geolocation_lng,
        10
    ) as geolocation_lng,

    cities.geolocation_city,
    states.geolocation_state,
    coordinates.source_location_records

from coordinate_medians as coordinates

left join ranked_cities as cities
    on coordinates.geolocation_zip_code_prefix
        = cities.geolocation_zip_code_prefix
    and cities.value_rank = 1

left join ranked_states as states
    on coordinates.geolocation_zip_code_prefix
        = states.geolocation_zip_code_prefix
    and states.value_rank = 1
