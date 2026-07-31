{% macro clean_string(expression) -%}
    nullif(
        trim(cast({{ expression }} as varchar)),
        ''
    )
{%- endmacro %}
