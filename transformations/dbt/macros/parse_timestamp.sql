{% macro parse_timestamp(expression) -%}
    try_cast(
        {{ clean_string(expression) }}
        as timestamp
    )
{%- endmacro %}
