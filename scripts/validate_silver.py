from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
LOG_DIR = PROJECT_ROOT / "logs"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


DATASET_RULES = {
    "silver_orders": {
        "primary_key": ["order_id"],
        "required_columns": [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_purchase_date",
            "delivery_delay_days",
            "actual_delivery_days",
        ],
    },
    "silver_order_items": {
        "primary_key": ["order_id", "order_item_id"],
        "required_columns": [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "price",
            "freight_value",
            "item_total_value",
        ],
    },
    "silver_payments": {
        "primary_key": [
            "order_id",
            "payment_sequential",
        ],
        "required_columns": [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
    },
    "silver_customers": {
        "primary_key": ["customer_id"],
        "required_columns": [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
    },
    "silver_customer_contact": {
        "primary_key": ["customer_id"],
        "required_columns": [
            "customer_id",
            "synthetic_email",
            "synthetic_phone",
        ],
    },
    "silver_products": {
        "primary_key": ["product_id"],
        "required_columns": [
            "product_id",
            "product_category_name",
            "product_name_length",
            "product_description_length",
        ],
    },
    "silver_product_categories": {
        "primary_key": ["product_category_name"],
        "required_columns": [
            "product_category_name",
            "product_category_name_english",
        ],
    },
    "silver_geolocation": {
        "primary_key": ["geolocation_zip_code_prefix"],
        "required_columns": [
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
            "geolocation_city",
            "geolocation_state",
            "source_location_records",
        ],
    },
    "silver_reviews": {
        "primary_key": ["review_record_id"],
        "required_columns": [
            "review_record_id",
            "review_id",
            "order_id",
            "review_score",
        ],
    },
    "silver_sellers": {
        "primary_key": ["seller_id"],
        "required_columns": [
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ],
    },
}


def load_dataset(dataset_name: str) -> pd.DataFrame:
    path = SILVER_DIR / f"{dataset_name}.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Silver dataset not found: {path}"
        )

    return pd.read_csv(path, low_memory=False)


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


def validate_dataset(
    dataset_name: str,
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    required_columns = rules["required_columns"]
    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    record_check(
        results,
        dataset_name,
        "required_columns_present",
        not missing_columns,
        ", ".join(missing_columns) if missing_columns else "none",
        "none missing",
        details="Required Silver schema columns.",
    )

    full_duplicates = int(
        dataframe.duplicated().sum()
    )

    record_check(
        results,
        dataset_name,
        "no_full_duplicate_rows",
        full_duplicates == 0,
        full_duplicates,
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


def validate_business_rules(
    datasets: dict[str, pd.DataFrame],
    results: list[dict[str, Any]],
) -> None:
    orders = datasets["silver_orders"]
    order_items = datasets["silver_order_items"]
    payments = datasets["silver_payments"]
    customers = datasets["silver_customers"]
    contacts = datasets["silver_customer_contact"]
    products = datasets["silver_products"]
    geolocation = datasets["silver_geolocation"]
    reviews = datasets["silver_reviews"]
    sellers = datasets["silver_sellers"]

    negative_prices = int(
        (order_items["price"] < 0).sum()
    )

    record_check(
        results,
        "silver_order_items",
        "price_non_negative",
        negative_prices == 0,
        negative_prices,
        0,
    )

    negative_freight = int(
        (order_items["freight_value"] < 0).sum()
    )

    record_check(
        results,
        "silver_order_items",
        "freight_non_negative",
        negative_freight == 0,
        negative_freight,
        0,
    )

    invalid_review_scores = int(
        (
            ~reviews["review_score"].between(
                1,
                5,
                inclusive="both",
            )
        ).sum()
    )

    record_check(
        results,
        "silver_reviews",
        "review_score_between_1_and_5",
        invalid_review_scores == 0,
        invalid_review_scores,
        0,
    )

    invalid_latitudes = int(
        (
            ~geolocation["geolocation_lat"].between(
                -90,
                90,
                inclusive="both",
            )
        ).sum()
    )

    invalid_longitudes = int(
        (
            ~geolocation["geolocation_lng"].between(
                -180,
                180,
                inclusive="both",
            )
        ).sum()
    )

    record_check(
        results,
        "silver_geolocation",
        "latitude_valid",
        invalid_latitudes == 0,
        invalid_latitudes,
        0,
    )

    record_check(
        results,
        "silver_geolocation",
        "longitude_valid",
        invalid_longitudes == 0,
        invalid_longitudes,
        0,
    )

    order_customer_orphans = int(
        (
            ~orders["customer_id"].isin(
                customers["customer_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_orders",
        "customer_foreign_key_valid",
        order_customer_orphans == 0,
        order_customer_orphans,
        0,
    )

    item_order_orphans = int(
        (
            ~order_items["order_id"].isin(
                orders["order_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_order_items",
        "order_foreign_key_valid",
        item_order_orphans == 0,
        item_order_orphans,
        0,
    )

    payment_order_orphans = int(
        (
            ~payments["order_id"].isin(
                orders["order_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_payments",
        "order_foreign_key_valid",
        payment_order_orphans == 0,
        payment_order_orphans,
        0,
    )

    item_product_orphans = int(
        (
            ~order_items["product_id"].isin(
                products["product_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_order_items",
        "product_foreign_key_valid",
        item_product_orphans == 0,
        item_product_orphans,
        0,
    )

    item_seller_orphans = int(
        (
            ~order_items["seller_id"].isin(
                sellers["seller_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_order_items",
        "seller_foreign_key_valid",
        item_seller_orphans == 0,
        item_seller_orphans,
        0,
    )

    review_order_orphans = int(
        (
            ~reviews["order_id"].isin(
                orders["order_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_reviews",
        "order_foreign_key_valid",
        review_order_orphans == 0,
        review_order_orphans,
        0,
    )

    contact_orphans = int(
        (
            ~contacts["customer_id"].isin(
                customers["customer_id"]
            )
        ).sum()
    )

    record_check(
        results,
        "silver_customer_contact",
        "customer_foreign_key_valid",
        contact_orphans == 0,
        contact_orphans,
        0,
    )

    contact_coverage = (
        contacts["customer_id"].nunique()
        / customers["customer_id"].nunique()
        * 100
    )

    record_check(
        results,
        "silver_customer_contact",
        "customer_contact_coverage",
        round(contact_coverage, 4) == 100.0,
        round(contact_coverage, 4),
        100.0,
    )


def main() -> None:
    started_at = datetime.now(timezone.utc)

    print("Starting Silver-layer validation...\n")

    results: list[dict[str, Any]] = []
    datasets: dict[str, pd.DataFrame] = {}

    for dataset_name, rules in DATASET_RULES.items():
        dataframe = load_dataset(dataset_name)
        datasets[dataset_name] = dataframe

        validate_dataset(
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
        RESULTS_DIR / "silver_validation_results.csv"
    )

    results_dataframe.to_csv(
        results_path,
        index=False,
    )

    passed_count = int(
        (results_dataframe["status"] == "PASS").sum()
    )

    failed_count = int(
        (results_dataframe["status"] == "FAIL").sum()
    )

    critical_failures = int(
        (
            (results_dataframe["status"] == "FAIL")
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
        "validation_started_at": started_at.isoformat(),
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
        "total_checks": len(results_dataframe),
        "passed_checks": passed_count,
        "failed_checks": failed_count,
        "critical_failures": critical_failures,
    }

    summary_path = (
        RESULTS_DIR / "silver_validation_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    log_path = LOG_DIR / "silver_validation.log"

    log_path.write_text(
        (
            "Silver validation completed.\n"
            f"Overall status: {overall_status}\n"
            f"Passed checks: {passed_count}\n"
            f"Failed checks: {failed_count}\n"
            f"Critical failures: {critical_failures}\n"
            f"Results: {results_path}\n"
            f"Summary: {summary_path}\n"
        ),
        encoding="utf-8",
    )

    print("\nSilver-layer validation completed.")
    print(f"Overall status: {overall_status}")
    print(f"Passed checks: {passed_count}")
    print(f"Failed checks: {failed_count}")
    print(f"Critical failures: {critical_failures}")
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")

    if critical_failures > 0:
        print("\nCritical failures:")
        print(
            results_dataframe[
                (
                    results_dataframe["status"]
                    == "FAIL"
                )
                & (
                    results_dataframe["severity"]
                    == "critical"
                )
            ][
                [
                    "dataset",
                    "check_name",
                    "observed_value",
                    "expected_value",
                ]
            ].to_string(index=False)
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()