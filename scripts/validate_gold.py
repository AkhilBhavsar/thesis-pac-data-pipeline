from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SILVER_DIR = PROJECT_ROOT / "data" / "silver"
GOLD_INTERNAL_DIR = PROJECT_ROOT / "data" / "gold" / "internal"
GOLD_PUBLIC_DIR = PROJECT_ROOT / "data" / "gold" / "public"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
LOG_DIR = PROJECT_ROOT / "logs"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

REVENUE_TOLERANCE = 5.0
ROW_CALCULATION_TOLERANCE = 0.02


DATASET_RULES = {
    "gold_daily_sales": {
        "path": GOLD_INTERNAL_DIR / "gold_daily_sales.csv",
        "primary_key": ["order_date"],
        "columns": [
            "order_date",
            "total_orders",
            "unique_customers",
            "units_sold",
            "product_revenue",
            "freight_revenue",
            "total_revenue",
            "average_order_value",
            "average_freight_value",
        ],
    },
    "gold_sales_by_state": {
        "path": GOLD_INTERNAL_DIR / "gold_sales_by_state.csv",
        "primary_key": ["customer_state"],
        "columns": [
            "customer_state",
            "total_orders",
            "unique_customers",
            "units_sold",
            "product_revenue",
            "freight_revenue",
            "total_revenue",
            "average_order_value",
        ],
    },
    "gold_product_category_revenue": {
        "path": (
            GOLD_INTERNAL_DIR
            / "gold_product_category_revenue.csv"
        ),
        "primary_key": [
            "product_category_name_english"
        ],
        "columns": [
            "product_category_name_english",
            "total_orders",
            "unique_customers",
            "units_sold",
            "product_revenue",
            "freight_revenue",
            "total_revenue",
            "average_item_price",
            "revenue_share_pct",
        ],
    },
    "gold_customer_order_summary": {
        "path": (
            GOLD_INTERNAL_DIR
            / "gold_customer_order_summary.csv"
        ),
        "primary_key": ["customer_unique_id"],
        "columns": [
            "customer_unique_id",
            "customer_state",
            "first_order_date",
            "latest_order_date",
            "total_orders",
            "total_items",
            "distinct_products",
            "product_revenue",
            "freight_revenue",
            "total_spend",
            "average_order_value",
        ],
    },
    "gold_public_sales_dashboard": {
        "path": (
            GOLD_PUBLIC_DIR
            / "gold_public_sales_dashboard.csv"
        ),
        "primary_key": [
            "order_date",
            "customer_state",
            "product_category_name_english",
        ],
        "columns": [
            "order_date",
            "customer_state",
            "product_category_name_english",
            "total_orders",
            "units_sold",
            "product_revenue",
            "freight_revenue",
            "total_revenue",
        ],
    },
}


FORBIDDEN_PUBLIC_COLUMN_PATTERNS = [
    "customer_id",
    "customer_unique_id",
    "order_id",
    "product_id",
    "seller_id",
    "review_id",
    "email",
    "phone",
    "address",
    "zip_code",
    "postal",
    "consent",
]


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Required dataset not found: {path}"
        )

    return pd.read_csv(
        path,
        low_memory=False,
    )


def record_check(
    results: list[dict[str, Any]],
    dataset: str,
    check_name: str,
    passed: bool,
    observed_value: Any,
    expected_value: Any,
    severity: str = "critical",
    details: str = "",
) -> None:
    results.append(
        {
            "dataset": dataset,
            "check_name": check_name,
            "status": "PASS" if passed else "FAIL",
            "severity": severity,
            "observed_value": observed_value,
            "expected_value": expected_value,
            "details": details,
        }
    )


def validate_structure(
    dataset_name: str,
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    expected_columns = rules["columns"]
    actual_columns = dataframe.columns.tolist()

    record_check(
        results,
        dataset_name,
        "contract_columns_exact",
        actual_columns == expected_columns,
        json.dumps(actual_columns),
        json.dumps(expected_columns),
        details=(
            "Column names and order must match the "
            "local Gold contract."
        ),
    )

    record_check(
        results,
        dataset_name,
        "dataset_not_empty",
        len(dataframe) > 0,
        len(dataframe),
        "> 0",
    )

    duplicate_rows = int(
        dataframe.duplicated().sum()
    )

    record_check(
        results,
        dataset_name,
        "no_full_duplicate_rows",
        duplicate_rows == 0,
        duplicate_rows,
        0,
    )

    primary_key = rules["primary_key"]

    missing_key_columns = [
        column
        for column in primary_key
        if column not in dataframe.columns
    ]

    if missing_key_columns:
        record_check(
            results,
            dataset_name,
            "primary_key_columns_present",
            False,
            ", ".join(missing_key_columns),
            "all present",
        )
        return

    null_key_rows = int(
        dataframe[primary_key]
        .isna()
        .any(axis=1)
        .sum()
    )

    duplicate_key_rows = int(
        dataframe.duplicated(
            subset=primary_key,
            keep=False,
        ).sum()
    )

    record_check(
        results,
        dataset_name,
        "primary_key_not_null",
        null_key_rows == 0,
        null_key_rows,
        0,
    )

    record_check(
        results,
        dataset_name,
        "primary_key_unique",
        duplicate_key_rows == 0,
        duplicate_key_rows,
        0,
    )

    null_cells = int(
        dataframe.isna().sum().sum()
    )

    record_check(
        results,
        dataset_name,
        "no_null_cells",
        null_cells == 0,
        null_cells,
        0,
    )


def validate_non_negative_metrics(
    dataset_name: str,
    dataframe: pd.DataFrame,
    columns: list[str],
    results: list[dict[str, Any]],
) -> None:
    for column in columns:
        invalid_rows = int(
            (dataframe[column] < 0).sum()
        )

        record_check(
            results,
            dataset_name,
            f"{column}_non_negative",
            invalid_rows == 0,
            invalid_rows,
            0,
        )


def validate_revenue_components(
    dataset_name: str,
    dataframe: pd.DataFrame,
    total_column: str,
    results: list[dict[str, Any]],
) -> None:
    difference = (
        dataframe["product_revenue"]
        + dataframe["freight_revenue"]
        - dataframe[total_column]
    ).abs()

    invalid_rows = int(
        (
            difference
            > ROW_CALCULATION_TOLERANCE
        ).sum()
    )

    record_check(
        results,
        dataset_name,
        "revenue_components_reconcile",
        invalid_rows == 0,
        invalid_rows,
        0,
        details=(
            "Product revenue plus freight revenue must "
            f"equal {total_column} within rounding tolerance."
        ),
    )


def validate_average(
    dataset_name: str,
    dataframe: pd.DataFrame,
    numerator_column: str,
    denominator_column: str,
    average_column: str,
    results: list[dict[str, Any]],
) -> None:
    expected = (
        dataframe[numerator_column]
        .div(
            dataframe[
                denominator_column
            ].replace(0, pd.NA)
        )
        .fillna(0)
    )

    difference = (
        expected
        - dataframe[average_column]
    ).abs()

    invalid_rows = int(
        (
            difference
            > ROW_CALCULATION_TOLERANCE
        ).sum()
    )

    record_check(
        results,
        dataset_name,
        f"{average_column}_correct",
        invalid_rows == 0,
        invalid_rows,
        0,
    )


def validate_dates(
    dataset_name: str,
    dataframe: pd.DataFrame,
    date_columns: list[str],
    results: list[dict[str, Any]],
) -> None:
    for column in date_columns:
        parsed = pd.to_datetime(
            dataframe[column],
            format="%Y-%m-%d",
            errors="coerce",
        )

        invalid_rows = int(
            parsed.isna().sum()
        )

        record_check(
            results,
            dataset_name,
            f"{column}_valid_date",
            invalid_rows == 0,
            invalid_rows,
            0,
        )


def validate_public_dataset(
    public_dashboard: pd.DataFrame,
    results: list[dict[str, Any]],
) -> None:
    public_columns_lower = [
        column.lower()
        for column in public_dashboard.columns
    ]

    forbidden_columns = sorted(
        {
            column
            for column in public_columns_lower
            if any(
                pattern in column
                for pattern
                in FORBIDDEN_PUBLIC_COLUMN_PATTERNS
            )
        }
    )

    record_check(
        results,
        "gold_public_sales_dashboard",
        "no_forbidden_public_columns",
        not forbidden_columns,
        (
            ", ".join(forbidden_columns)
            if forbidden_columns
            else "none"
        ),
        "none",
        details=(
            "Public output must not contain direct "
            "identifiers or contact attributes."
        ),
    )

    text_columns = [
        column
        for column in [
            "customer_state",
            "product_category_name_english",
        ]
        if column in public_dashboard.columns
    ]

    combined_text = (
        public_dashboard[text_columns]
        .astype("string")
        .fillna("")
        .agg(" ".join, axis=1)
    )

    email_pattern = re.compile(
        r"\b[A-Za-z0-9._%+-]+@"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    phone_pattern = re.compile(
        r"(?<!\d)"
        r"(?:\+?\d[\s().-]*){8,}"
        r"(?!\d)"
    )

    email_matches = int(
        combined_text.str.contains(
            email_pattern,
            regex=True,
            na=False,
        ).sum()
    )

    phone_matches = int(
        combined_text.str.contains(
            phone_pattern,
            regex=True,
            na=False,
        ).sum()
    )

    record_check(
        results,
        "gold_public_sales_dashboard",
        "no_email_like_values",
        email_matches == 0,
        email_matches,
        0,
    )

    record_check(
        results,
        "gold_public_sales_dashboard",
        "no_phone_like_values",
        phone_matches == 0,
        phone_matches,
        0,
    )


def validate_source_reconciliation(
    datasets: dict[str, pd.DataFrame],
    results: list[dict[str, Any]],
) -> None:
    orders = load_csv(
        SILVER_DIR / "silver_orders.csv"
    )

    order_items = load_csv(
        SILVER_DIR / "silver_order_items.csv"
    )

    orders["order_status"] = (
        orders["order_status"]
        .astype("string")
        .str.lower()
    )

    delivered_order_ids = set(
        orders.loc[
            orders["order_status"] == "delivered",
            "order_id",
        ]
    )

    delivered_items = order_items[
        order_items["order_id"].isin(
            delivered_order_ids
        )
    ].copy()

    for column in [
        "price",
        "freight_value",
        "item_total_value",
    ]:
        delivered_items[column] = pd.to_numeric(
            delivered_items[column],
            errors="coerce",
        ).fillna(0)

    base_orders = len(delivered_order_ids)
    base_items = len(delivered_items)

    base_product_revenue = float(
        delivered_items["price"].sum()
    )

    base_freight_revenue = float(
        delivered_items["freight_value"].sum()
    )

    base_total_revenue = float(
        delivered_items[
            "item_total_value"
        ].sum()
    )

    daily = datasets["gold_daily_sales"]
    state = datasets["gold_sales_by_state"]
    category = datasets[
        "gold_product_category_revenue"
    ]
    customer = datasets[
        "gold_customer_order_summary"
    ]
    public = datasets[
        "gold_public_sales_dashboard"
    ]

    order_count_checks = {
        "gold_daily_sales": int(
            daily["total_orders"].sum()
        ),
        "gold_sales_by_state": int(
            state["total_orders"].sum()
        ),
        "gold_customer_order_summary": int(
            customer["total_orders"].sum()
        ),
    }

    for dataset_name, observed in (
        order_count_checks.items()
    ):
        record_check(
            results,
            dataset_name,
            "delivered_order_count_reconciles",
            observed == base_orders,
            observed,
            base_orders,
        )

    item_count_checks = {
        "gold_daily_sales": int(
            daily["units_sold"].sum()
        ),
        "gold_sales_by_state": int(
            state["units_sold"].sum()
        ),
        "gold_product_category_revenue": int(
            category["units_sold"].sum()
        ),
        "gold_customer_order_summary": int(
            customer["total_items"].sum()
        ),
        "gold_public_sales_dashboard": int(
            public["units_sold"].sum()
        ),
    }

    for dataset_name, observed in (
        item_count_checks.items()
    ):
        record_check(
            results,
            dataset_name,
            "delivered_item_count_reconciles",
            observed == base_items,
            observed,
            base_items,
        )

    revenue_checks = {
        "gold_daily_sales": float(
            daily["total_revenue"].sum()
        ),
        "gold_sales_by_state": float(
            state["total_revenue"].sum()
        ),
        "gold_product_category_revenue": float(
            category["total_revenue"].sum()
        ),
        "gold_customer_order_summary": float(
            customer["total_spend"].sum()
        ),
        "gold_public_sales_dashboard": float(
            public["total_revenue"].sum()
        ),
    }

    for dataset_name, observed in (
        revenue_checks.items()
    ):
        difference = abs(
            observed - base_total_revenue
        )

        record_check(
            results,
            dataset_name,
            "total_revenue_reconciles",
            difference <= REVENUE_TOLERANCE,
            round(observed, 2),
            round(base_total_revenue, 2),
            details=(
                f"Absolute difference: {difference:.4f}; "
                f"allowed tolerance: {REVENUE_TOLERANCE:.2f}"
            ),
        )

    product_revenue_checks = {
        "gold_daily_sales": float(
            daily["product_revenue"].sum()
        ),
        "gold_sales_by_state": float(
            state["product_revenue"].sum()
        ),
        "gold_product_category_revenue": float(
            category["product_revenue"].sum()
        ),
        "gold_customer_order_summary": float(
            customer["product_revenue"].sum()
        ),
        "gold_public_sales_dashboard": float(
            public["product_revenue"].sum()
        ),
    }

    for dataset_name, observed in (
        product_revenue_checks.items()
    ):
        difference = abs(
            observed - base_product_revenue
        )

        record_check(
            results,
            dataset_name,
            "product_revenue_reconciles",
            difference <= REVENUE_TOLERANCE,
            round(observed, 2),
            round(base_product_revenue, 2),
            details=(
                f"Absolute difference: {difference:.4f}"
            ),
        )

    freight_revenue_checks = {
        "gold_daily_sales": float(
            daily["freight_revenue"].sum()
        ),
        "gold_sales_by_state": float(
            state["freight_revenue"].sum()
        ),
        "gold_product_category_revenue": float(
            category["freight_revenue"].sum()
        ),
        "gold_customer_order_summary": float(
            customer["freight_revenue"].sum()
        ),
        "gold_public_sales_dashboard": float(
            public["freight_revenue"].sum()
        ),
    }

    for dataset_name, observed in (
        freight_revenue_checks.items()
    ):
        difference = abs(
            observed - base_freight_revenue
        )

        record_check(
            results,
            dataset_name,
            "freight_revenue_reconciles",
            difference <= REVENUE_TOLERANCE,
            round(observed, 2),
            round(base_freight_revenue, 2),
            details=(
                f"Absolute difference: {difference:.4f}"
            ),
        )


def validate_business_rules(
    datasets: dict[str, pd.DataFrame],
    results: list[dict[str, Any]],
) -> None:
    daily = datasets["gold_daily_sales"]
    state = datasets["gold_sales_by_state"]
    category = datasets[
        "gold_product_category_revenue"
    ]
    customer = datasets[
        "gold_customer_order_summary"
    ]
    public = datasets[
        "gold_public_sales_dashboard"
    ]

    common_sales_metrics = [
        "total_orders",
        "units_sold",
        "product_revenue",
        "freight_revenue",
        "total_revenue",
    ]

    validate_non_negative_metrics(
        "gold_daily_sales",
        daily,
        common_sales_metrics
        + [
            "unique_customers",
            "average_order_value",
            "average_freight_value",
        ],
        results,
    )

    validate_non_negative_metrics(
        "gold_sales_by_state",
        state,
        common_sales_metrics
        + [
            "unique_customers",
            "average_order_value",
        ],
        results,
    )

    validate_non_negative_metrics(
        "gold_product_category_revenue",
        category,
        common_sales_metrics
        + [
            "unique_customers",
            "average_item_price",
            "revenue_share_pct",
        ],
        results,
    )

    validate_non_negative_metrics(
        "gold_customer_order_summary",
        customer,
        [
            "total_orders",
            "total_items",
            "distinct_products",
            "product_revenue",
            "freight_revenue",
            "total_spend",
            "average_order_value",
        ],
        results,
    )

    validate_non_negative_metrics(
        "gold_public_sales_dashboard",
        public,
        common_sales_metrics,
        results,
    )

    validate_revenue_components(
        "gold_daily_sales",
        daily,
        "total_revenue",
        results,
    )

    validate_revenue_components(
        "gold_sales_by_state",
        state,
        "total_revenue",
        results,
    )

    validate_revenue_components(
        "gold_product_category_revenue",
        category,
        "total_revenue",
        results,
    )

    validate_revenue_components(
        "gold_customer_order_summary",
        customer,
        "total_spend",
        results,
    )

    validate_revenue_components(
        "gold_public_sales_dashboard",
        public,
        "total_revenue",
        results,
    )

    validate_average(
        "gold_daily_sales",
        daily,
        "total_revenue",
        "total_orders",
        "average_order_value",
        results,
    )

    validate_average(
        "gold_daily_sales",
        daily,
        "freight_revenue",
        "total_orders",
        "average_freight_value",
        results,
    )

    validate_average(
        "gold_sales_by_state",
        state,
        "total_revenue",
        "total_orders",
        "average_order_value",
        results,
    )

    validate_average(
        "gold_product_category_revenue",
        category,
        "product_revenue",
        "units_sold",
        "average_item_price",
        results,
    )

    validate_average(
        "gold_customer_order_summary",
        customer,
        "total_spend",
        "total_orders",
        "average_order_value",
        results,
    )

    validate_dates(
        "gold_daily_sales",
        daily,
        ["order_date"],
        results,
    )

    validate_dates(
        "gold_customer_order_summary",
        customer,
        [
            "first_order_date",
            "latest_order_date",
        ],
        results,
    )

    validate_dates(
        "gold_public_sales_dashboard",
        public,
        ["order_date"],
        results,
    )

    first_dates = pd.to_datetime(
        customer["first_order_date"],
        errors="coerce",
    )

    latest_dates = pd.to_datetime(
        customer["latest_order_date"],
        errors="coerce",
    )

    invalid_date_order = int(
        (first_dates > latest_dates).sum()
    )

    record_check(
        results,
        "gold_customer_order_summary",
        "first_order_not_after_latest_order",
        invalid_date_order == 0,
        invalid_date_order,
        0,
    )

    invalid_product_counts = int(
        (
            customer["distinct_products"]
            > customer["total_items"]
        ).sum()
    )

    record_check(
        results,
        "gold_customer_order_summary",
        "distinct_products_not_above_items",
        invalid_product_counts == 0,
        invalid_product_counts,
        0,
    )

    invalid_daily_customers = int(
        (
            daily["unique_customers"]
            > daily["total_orders"]
        ).sum()
    )

    record_check(
        results,
        "gold_daily_sales",
        "unique_customers_not_above_orders",
        invalid_daily_customers == 0,
        invalid_daily_customers,
        0,
    )

    revenue_share_sum = float(
        category["revenue_share_pct"].sum()
    )

    record_check(
        results,
        "gold_product_category_revenue",
        "revenue_share_sums_to_100",
        abs(revenue_share_sum - 100.0) <= 0.1,
        round(revenue_share_sum, 4),
        100.0,
    )

    valid_states = (
        state["customer_state"]
        .astype("string")
        .str.match(
            r"^(?:[A-Z]{2}|UNKNOWN)$",
            na=False,
        )
    )

    invalid_states = int(
        (~valid_states).sum()
    )

    record_check(
        results,
        "gold_sales_by_state",
        "customer_state_format_valid",
        invalid_states == 0,
        invalid_states,
        0,
    )

    validate_public_dataset(
        public,
        results,
    )

    validate_source_reconciliation(
        datasets,
        results,
    )


def main() -> None:
    started_at = datetime.now(timezone.utc)

    print("Starting Gold-layer validation...\n")

    datasets: dict[str, pd.DataFrame] = {}
    results: list[dict[str, Any]] = []

    for dataset_name, rules in (
        DATASET_RULES.items()
    ):
        dataframe = load_csv(rules["path"])
        datasets[dataset_name] = dataframe

        validate_structure(
            dataset_name,
            dataframe,
            rules,
            results,
        )

        print(
            f"Validated structure: {dataset_name} "
            f"({len(dataframe):,} rows)"
        )

    validate_business_rules(
        datasets,
        results,
    )

    completed_at = datetime.now(timezone.utc)

    results_dataframe = pd.DataFrame(results)

    results_path = (
        RESULTS_DIR
        / "gold_validation_results.csv"
    )

    results_dataframe.to_csv(
        results_path,
        index=False,
    )

    passed_checks = int(
        (
            results_dataframe["status"]
            == "PASS"
        ).sum()
    )

    failed_checks = int(
        (
            results_dataframe["status"]
            == "FAIL"
        ).sum()
    )

    critical_failures = int(
        (
            (
                results_dataframe["status"]
                == "FAIL"
            )
            & (
                results_dataframe["severity"]
                == "critical"
            )
        ).sum()
    )

    overall_status = (
        "PASS"
        if critical_failures == 0
        else "FAIL"
    )

    summary = {
        "validation_started_at": (
            started_at.isoformat()
        ),
        "validation_completed_at": (
            completed_at.isoformat()
        ),
        "duration_seconds": round(
            (
                completed_at
                - started_at
            ).total_seconds(),
            4,
        ),
        "overall_status": overall_status,
        "total_checks": len(
            results_dataframe
        ),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "critical_failures": (
            critical_failures
        ),
    }

    summary_path = (
        RESULTS_DIR
        / "gold_validation_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    log_path = (
        LOG_DIR / "gold_validation.log"
    )

    log_path.write_text(
        (
            "Gold validation completed.\n"
            f"Overall status: {overall_status}\n"
            f"Passed checks: {passed_checks}\n"
            f"Failed checks: {failed_checks}\n"
            f"Critical failures: "
            f"{critical_failures}\n"
            f"Results: {results_path}\n"
            f"Summary: {summary_path}\n"
        ),
        encoding="utf-8",
    )

    print("\nGold-layer validation completed.")
    print(f"Overall status: {overall_status}")
    print(f"Passed checks: {passed_checks}")
    print(f"Failed checks: {failed_checks}")
    print(
        f"Critical failures: "
        f"{critical_failures}"
    )
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")

    if critical_failures > 0:
        failures = results_dataframe[
            (
                results_dataframe["status"]
                == "FAIL"
            )
            & (
                results_dataframe["severity"]
                == "critical"
            )
        ]

        print("\nCritical failures:")
        print(
            failures[
                [
                    "dataset",
                    "check_name",
                    "observed_value",
                    "expected_value",
                    "details",
                ]
            ].to_string(index=False)
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()