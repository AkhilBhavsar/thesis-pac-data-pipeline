{% macro zone_external_location(zone, dataset_name) -%}
    {{ return(
        's3://'
        ~ env_var(
            'DBT_ATHENA_DATA_BUCKET',
            'thesis-pac-dev-data-lake-522814714524-eu-west-1'
        )
        ~ '/'
        ~ zone
        ~ '/'
        ~ dataset_name
        ~ '/'
        ~ invocation_id
        ~ '/'
    ) }}
{%- endmacro %}
