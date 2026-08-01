{% macro fractional_days_between(start_expression, end_expression) -%}
    (
        cast(
            date_diff(
                'second',
                {{ start_expression }},
                {{ end_expression }}
            )
            as double
        )
        / 86400.0
    )
{%- endmacro %}
