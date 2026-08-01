{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}

    {%- set governed_exact_schemas = [
        'thesis_pac_dev_gold_internal',
        'thesis_pac_dev_gold_public'
    ] -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}

    {%- elif custom_schema_name | trim in governed_exact_schemas -%}
        {{ custom_schema_name | trim }}

    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
