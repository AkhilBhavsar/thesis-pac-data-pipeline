{% macro zone_external_location(zone, dataset_name) -%}
    {%- set configured_root = env_var(
        'DBT_ZONE_EXTERNAL_ROOT',
        ''
    ) | trim -%}

    {%- if configured_root -%}
        {%- set normalized_root = configured_root | trim('/') -%}

        {{ return(
            normalized_root
            ~ '/'
            ~ zone
            ~ '/'
            ~ dataset_name
            ~ '/'
            ~ invocation_id
            ~ '/'
        ) }}

    {%- else -%}
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
    {%- endif -%}
{%- endmacro %}
