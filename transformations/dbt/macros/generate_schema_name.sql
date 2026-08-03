{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}

    {%- set gold_internal_schema = env_var(
        'DBT_GOLD_INTERNAL_SCHEMA',
        'thesis_pac_dev_gold_internal'
    ) | trim -%}

    {%- set gold_public_schema = env_var(
        'DBT_GOLD_PUBLIC_SCHEMA',
        'thesis_pac_dev_gold_public'
    ) | trim -%}

    {%- set governed_exact_schemas = [
        gold_internal_schema,
        gold_public_schema
    ] -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}

    {%- elif custom_schema_name | trim in governed_exact_schemas -%}
        {{ custom_schema_name | trim }}

    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
