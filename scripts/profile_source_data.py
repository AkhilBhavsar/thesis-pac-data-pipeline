from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


BASE_DIR = Path(".")
RAW_DIR = BASE_DIR / "data" / "bronze" / "raw" / "olist"
GENERATED_DIR = BASE_DIR / "data" / "bronze" / "generated"
PROFILE_DIR = BASE_DIR / "data" / "profile"
LOG_DIR = BASE_DIR / "logs"

PROFILE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


DATASETS = {
    "customers": {
        "path": RAW_DIR / "olist_customers_dataset.csv",
        "primary_key": ["customer_id"],
        "date_columns": [],
    },
    "geolocation": {
        "path": RAW_DIR / "olist_geolocation_dataset.csv",
        "primary_key": [],
        "date_columns": [],
    },
    "order_items": {
        "path": RAW_DIR / "olist_order_items_dataset.csv",
        "primary_key": ["order_id", "order_item_id"],
        "date_columns": ["shipping_limit_date"],
    },
    "payments": {
        "path": RAW_DIR / "olist_order_payments_dataset.csv",
        "primary_key": ["order_id", "payment_sequential"],
        "date_columns": [],
    },
    "reviews": {
        "path": RAW_DIR / "olist_order_reviews_dataset.csv",
        "primary_key": ["review_id"],
        "date_columns": [
            "review_creation_date",
            "review_answer_timestamp",
        ],
    },
    "orders": {
        "path": RAW_DIR / "olist_orders_dataset.csv",
        "primary_key": ["order_id"],
        "date_columns": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    },
    "products": {
        "path": RAW_DIR / "olist_products_dataset.csv",
        "primary_key": ["product_id"],
        "date_columns": [],
    },
    "sellers": {
        "path": RAW_DIR / "olist_sellers_dataset.csv",
        "primary_key": ["seller_id"],
        "date_columns": [],
    },
    "product_category_translation": {
        "path": RAW_DIR / "product_category_name_translation.csv",
        "primary_key": ["product_category_name"],
        "date_columns": [],
    },
    "synthetic_customer_contact": {
        "path": GENERATED_DIR / "synthetic_customer_contact.csv",
        "primary_key": ["customer_id"],
        "date_columns": [],
    },
    "freshness_control": {
        "path": GENERATED_DIR / "freshness_control.csv",
        "primary_key": ["dataset_name", "run_id"],
        "date_columns": [
            "expected_publish_time",
            "actual_publish_time",
        ],
    },
}


def safe_json_value(value):
    """Convert pandas/numpy values into JSON-compatible values."""
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if hasattr(value, "item"):
        return value.item()

    return value


def profile_dataset(
    dataset_name: str,
    dataset_config: dict,
) -> tuple[dict, list[dict]]:
    path = dataset_config["path"]

    if not path.exists():
        raise FileNotFoundError(
            f"Required dataset was not found: {path}"
        )

    dataframe = pd.read_csv(path, low_memory=False)

    row_count = len(dataframe)
    column_count = len(dataframe.columns)

    duplicate_full_rows = int(dataframe.duplicated().sum())

    primary_key = dataset_config["primary_key"]

    if primary_key:
        missing_key_columns = [
            column
            for column in primary_key
            if column not in dataframe.columns
        ]

        if missing_key_columns:
            raise ValueError(
                f"{dataset_name}: primary-key columns missing: "
                f"{missing_key_columns}"
            )

        duplicate_primary_keys = int(
            dataframe.duplicated(
                subset=primary_key,
                keep=False,
            ).sum()
        )

        null_primary_key_rows = int(
            dataframe[primary_key]
            .isna()
            .any(axis=1)
            .sum()
        )

    else:
        duplicate_primary_keys = None
        null_primary_key_rows = None

    column_profiles = []

    for column in dataframe.columns:
        series = dataframe[column]

        null_count = int(series.isna().sum())

        null_percentage = (
            round((null_count / row_count) * 100, 4)
            if row_count
            else 0
        )

        unique_count = int(series.nunique(dropna=True))

        sample_values = [
            safe_json_value(value)
            for value in series.dropna().head(3).tolist()
        ]

        column_profiles.append(
            {
                "dataset": dataset_name,
                "column": column,
                "dtype": str(series.dtype),
                "row_count": row_count,
                "null_count": null_count,
                "null_percentage": null_percentage,
                "unique_count": unique_count,
                "sample_values": " | ".join(
                    map(str, sample_values)
                ),
            }
        )

    date_ranges = {}

    for column in dataset_config["date_columns"]:
        if column not in dataframe.columns:
            continue

        parsed_dates = pd.to_datetime(
            dataframe[column],
            errors="coerce",
            utc=True,
        )

        date_ranges[column] = {
            "minimum": (
                parsed_dates.min().isoformat()
                if parsed_dates.notna().any()
                else None
            ),
            "maximum": (
                parsed_dates.max().isoformat()
                if parsed_dates.notna().any()
                else None
            ),
            "invalid_or_missing_count": int(
                parsed_dates.isna().sum()
            ),
        }

    numeric_summary = {}

    numeric_columns = dataframe.select_dtypes(
        include="number"
    ).columns

    for column in numeric_columns:
        description = dataframe[column].describe()

        numeric_summary[column] = {
            key: safe_json_value(value)
            for key, value in description.to_dict().items()
        }

    dataset_summary = {
        "dataset": dataset_name,
        "source_path": str(path),
        "row_count": row_count,
        "column_count": column_count,
        "columns": dataframe.columns.tolist(),
        "duplicate_full_rows": duplicate_full_rows,
        "primary_key": primary_key,
        "duplicate_primary_key_rows": (
            duplicate_primary_keys
        ),
        "null_primary_key_rows": null_primary_key_rows,
        "date_ranges": date_ranges,
        "numeric_summary": numeric_summary,
    }

    return dataset_summary, column_profiles


def main() -> None:
    all_dataset_summaries = []
    all_column_profiles = []

    print("Starting source-data profiling...\n")

    for dataset_name, dataset_config in DATASETS.items():
        print(f"Profiling: {dataset_name}")

        summary, column_profiles = profile_dataset(
            dataset_name,
            dataset_config,
        )

        all_dataset_summaries.append(summary)
        all_column_profiles.extend(column_profiles)

        print(
            f"  Rows: {summary['row_count']:,}"
            f" | Columns: {summary['column_count']}"
            f" | Full duplicates: "
            f"{summary['duplicate_full_rows']:,}"
        )

    dataset_summary_dataframe = pd.DataFrame(
        [
            {
                "dataset": item["dataset"],
                "source_path": item["source_path"],
                "row_count": item["row_count"],
                "column_count": item["column_count"],
                "duplicate_full_rows": (
                    item["duplicate_full_rows"]
                ),
                "primary_key": ", ".join(
                    item["primary_key"]
                ),
                "duplicate_primary_key_rows": (
                    item["duplicate_primary_key_rows"]
                ),
                "null_primary_key_rows": (
                    item["null_primary_key_rows"]
                ),
            }
            for item in all_dataset_summaries
        ]
    )

    column_profile_dataframe = pd.DataFrame(
        all_column_profiles
    )

    dataset_summary_path = (
        PROFILE_DIR / "dataset_summary.csv"
    )

    column_profile_path = (
        PROFILE_DIR / "column_profile.csv"
    )

    detailed_profile_path = (
        PROFILE_DIR / "detailed_profile.json"
    )

    dataset_summary_dataframe.to_csv(
        dataset_summary_path,
        index=False,
    )

    column_profile_dataframe.to_csv(
        column_profile_path,
        index=False,
    )

    detailed_profile_path.write_text(
        json.dumps(
            {
                "profile_generated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "datasets": all_dataset_summaries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    log_path = LOG_DIR / "source_profile.log"

    log_path.write_text(
        (
            "Source-data profiling completed successfully.\n"
            f"Generated at: "
            f"{datetime.now(timezone.utc).isoformat()}\n"
            f"Datasets profiled: "
            f"{len(all_dataset_summaries)}\n"
            f"Dataset summary: {dataset_summary_path}\n"
            f"Column profile: {column_profile_path}\n"
            f"Detailed profile: {detailed_profile_path}\n"
        ),
        encoding="utf-8",
    )

    print("\nProfiling completed successfully.")
    print(f"Created: {dataset_summary_path}")
    print(f"Created: {column_profile_path}")
    print(f"Created: {detailed_profile_path}")
    print(f"Created: {log_path}")


if __name__ == "__main__":
    main()