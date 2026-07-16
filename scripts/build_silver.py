from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "data" / "bronze" / "raw" / "olist"
GENERATED_DIR = PROJECT_ROOT / "data" / "bronze" / "generated"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
LOG_DIR = PROJECT_ROOT / "logs"

SILVER_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


SOURCE_FILES = {
    "customers": RAW_DIR / "olist_customers_dataset.csv",
    "geolocation": RAW_DIR / "olist_geolocation_dataset.csv",
    "order_items": RAW_DIR / "olist_order_items_dataset.csv",
    "payments": RAW_DIR / "olist_order_payments_dataset.csv",
    "reviews": RAW_DIR / "olist_order_reviews_dataset.csv",
    "orders": RAW_DIR / "olist_orders_dataset.csv",
    "products": RAW_DIR / "olist_products_dataset.csv",
    "sellers": RAW_DIR / "olist_sellers_dataset.csv",
    "product_categories": (
        RAW_DIR / "product_category_name_translation.csv"
    ),
    "customer_contact": (
        GENERATED_DIR / "synthetic_customer_contact.csv"
    ),
}


def require_file(path: Path) -> None:
    """Raise a clear error when a required source file is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required source file not found: {path}")


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV source using consistent settings."""
    require_file(path)
    return pd.read_csv(path, low_memory=False)


def clean_string_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Trim string values and convert empty strings to pandas missing values.
    """
    cleaned = dataframe.copy()

    for column in cleaned.select_dtypes(
        include=["object", "string"]
    ).columns:
        cleaned[column] = (
            cleaned[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )

    return cleaned


def parse_datetime_columns(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Parse selected columns into UTC-aware timestamps."""
    parsed = dataframe.copy()

    for column in columns:
        if column in parsed.columns:
            parsed[column] = pd.to_datetime(
                parsed[column],
                errors="coerce",
                utc=True,
            )

    return parsed


def convert_numeric_columns(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Convert selected columns to numeric values."""
    converted = dataframe.copy()

    for column in columns:
        if column in converted.columns:
            converted[column] = pd.to_numeric(
                converted[column],
                errors="coerce",
            )

    return converted


def representative_mode(series: pd.Series) -> Any:
    """
    Return a deterministic representative mode.

    If several values have the same frequency, the alphabetically first
    value is used.
    """
    values = series.dropna().astype("string")

    if values.empty:
        return pd.NA

    counts = values.value_counts()
    highest_count = counts.max()

    candidates = sorted(
        counts[counts == highest_count].index.astype(str)
    )

    return candidates[0]


def dataframe_hash(dataframe: pd.DataFrame) -> str:
    """Create a deterministic SHA-256 hash for an output dataset."""
    hashed_values = pd.util.hash_pandas_object(
        dataframe,
        index=True,
    ).values

    return hashlib.sha256(
        hashed_values.tobytes()
    ).hexdigest()


def write_silver_dataset(
    dataset_name: str,
    dataframe: pd.DataFrame,
    source_rows: int,
    notes: str,
) -> dict[str, Any]:
    """Write a Silver CSV and return manifest information."""
    output_path = SILVER_DIR / f"{dataset_name}.csv"

    dataframe.to_csv(
        output_path,
        index=False,
        date_format="%Y-%m-%dT%H:%M:%S%z",
    )

    return {
        "dataset": dataset_name,
        "output_path": str(output_path.relative_to(PROJECT_ROOT)),
        "source_rows": source_rows,
        "silver_rows": len(dataframe),
        "column_count": len(dataframe.columns),
        "full_duplicate_rows": int(
            dataframe.duplicated().sum()
        ),
        "dataset_hash_sha256": dataframe_hash(dataframe),
        "notes": notes,
    }


def build_orders() -> tuple[pd.DataFrame, int]:
    orders = read_csv(SOURCE_FILES["orders"])
    source_rows = len(orders)

    orders = clean_string_columns(orders)

    orders = parse_datetime_columns(
        orders,
        [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    )

    orders = orders.drop_duplicates().copy()

    orders["order_purchase_date"] = (
        orders["order_purchase_timestamp"].dt.date
    )

    orders["delivery_delay_days"] = (
        (
            orders["order_delivered_customer_date"]
            - orders["order_estimated_delivery_date"]
        )
        .dt.total_seconds()
        .div(86400)
    )

    orders["actual_delivery_days"] = (
        (
            orders["order_delivered_customer_date"]
            - orders["order_purchase_timestamp"]
        )
        .dt.total_seconds()
        .div(86400)
    )

    return orders, source_rows


def build_order_items() -> tuple[pd.DataFrame, int]:
    order_items = read_csv(SOURCE_FILES["order_items"])
    source_rows = len(order_items)

    order_items = clean_string_columns(order_items)

    order_items = parse_datetime_columns(
        order_items,
        ["shipping_limit_date"],
    )

    order_items = convert_numeric_columns(
        order_items,
        [
            "order_item_id",
            "price",
            "freight_value",
        ],
    )

    order_items = order_items.drop_duplicates().copy()

    order_items["item_total_value"] = (
        order_items["price"]
        + order_items["freight_value"]
    )

    return order_items, source_rows


def build_payments() -> tuple[pd.DataFrame, int]:
    payments = read_csv(SOURCE_FILES["payments"])
    source_rows = len(payments)

    payments = clean_string_columns(payments)

    payments = convert_numeric_columns(
        payments,
        [
            "payment_sequential",
            "payment_installments",
            "payment_value",
        ],
    )

    payments = payments.drop_duplicates().copy()

    return payments, source_rows


def build_customers() -> tuple[pd.DataFrame, int]:
    customers = read_csv(SOURCE_FILES["customers"])
    source_rows = len(customers)

    customers = clean_string_columns(customers)
    customers = customers.drop_duplicates().copy()

    customers["customer_zip_code_prefix"] = pd.to_numeric(
        customers["customer_zip_code_prefix"],
        errors="coerce",
    ).astype("Int64")

    customers["customer_city"] = (
        customers["customer_city"].str.lower()
    )

    customers["customer_state"] = (
        customers["customer_state"].str.upper()
    )

    return customers, source_rows


def build_customer_contact() -> tuple[pd.DataFrame, int]:
    contact = read_csv(SOURCE_FILES["customer_contact"])
    source_rows = len(contact)

    contact = clean_string_columns(contact)
    contact = contact.drop_duplicates().copy()

    if "synthetic_email" in contact.columns:
        contact["synthetic_email"] = (
            contact["synthetic_email"].str.lower()
        )

    if "consent_flag" in contact.columns:
        contact["consent_flag"] = (
            contact["consent_flag"]
            .astype("string")
            .str.lower()
            .map(
                {
                    "true": True,
                    "false": False,
                    "yes": True,
                    "no": False,
                    "1": True,
                    "0": False,
                }
            )
            .astype("boolean")
        )

    return contact, source_rows


def build_products() -> tuple[pd.DataFrame, int]:
    products = read_csv(SOURCE_FILES["products"])
    source_rows = len(products)

    products = clean_string_columns(products)

    products = products.rename(
        columns={
            "product_name_lenght": "product_name_length",
            "product_description_lenght": (
                "product_description_length"
            ),
        }
    )

    products = convert_numeric_columns(
        products,
        [
            "product_name_length",
            "product_description_length",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
    )

    products = products.drop_duplicates().copy()

    return products, source_rows


def build_product_categories() -> tuple[pd.DataFrame, int]:
    categories = read_csv(
        SOURCE_FILES["product_categories"]
    )
    source_rows = len(categories)

    categories = clean_string_columns(categories)
    categories = categories.drop_duplicates().copy()

    categories["product_category_name"] = (
        categories["product_category_name"].str.lower()
    )

    categories["product_category_name_english"] = (
        categories["product_category_name_english"]
        .str.lower()
    )

    return categories, source_rows


def build_geolocation() -> tuple[pd.DataFrame, int]:
    geolocation = read_csv(SOURCE_FILES["geolocation"])
    source_rows = len(geolocation)

    geolocation = clean_string_columns(geolocation)

    geolocation = convert_numeric_columns(
        geolocation,
        [
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
        ],
    )

    geolocation = geolocation.drop_duplicates().copy()

    geolocation["geolocation_city"] = (
        geolocation["geolocation_city"].str.lower()
    )

    geolocation["geolocation_state"] = (
        geolocation["geolocation_state"].str.upper()
    )

    geolocation = geolocation.dropna(
        subset=["geolocation_zip_code_prefix"]
    )

    geolocation["geolocation_zip_code_prefix"] = (
        geolocation["geolocation_zip_code_prefix"]
        .astype("Int64")
    )

    aggregated = (
        geolocation.groupby(
            "geolocation_zip_code_prefix",
            as_index=False,
            dropna=False,
        )
        .agg(
            geolocation_lat=(
                "geolocation_lat",
                "median",
            ),
            geolocation_lng=(
                "geolocation_lng",
                "median",
            ),
            geolocation_city=(
                "geolocation_city",
                representative_mode,
            ),
            geolocation_state=(
                "geolocation_state",
                representative_mode,
            ),
            source_location_records=(
                "geolocation_zip_code_prefix",
                "size",
            ),
        )
    )

    return aggregated, source_rows


def build_reviews() -> tuple[pd.DataFrame, int]:
    reviews = read_csv(SOURCE_FILES["reviews"])
    source_rows = len(reviews)

    reviews = clean_string_columns(reviews)

    reviews = parse_datetime_columns(
        reviews,
        [
            "review_creation_date",
            "review_answer_timestamp",
        ],
    )

    reviews = convert_numeric_columns(
        reviews,
        ["review_score"],
    )

    reviews = reviews.drop_duplicates().copy()

    reviews = reviews.sort_values(
        by=[
            "review_id",
            "order_id",
            "review_creation_date",
            "review_answer_timestamp",
        ],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    reviews["review_occurrence"] = (
        reviews.groupby(
            [
                "review_id",
                "order_id",
                "review_creation_date",
                "review_answer_timestamp",
            ],
            dropna=False,
        )
        .cumcount()
        .add(1)
    )

    def create_review_record_id(row: pd.Series) -> str:
        values = [
            row.get("review_id"),
            row.get("order_id"),
            row.get("review_creation_date"),
            row.get("review_answer_timestamp"),
            row.get("review_occurrence"),
        ]

        raw_key = "|".join(
            "" if pd.isna(value) else str(value)
            for value in values
        )

        return hashlib.sha256(
            raw_key.encode("utf-8")
        ).hexdigest()

    reviews.insert(
        0,
        "review_record_id",
        reviews.apply(
            create_review_record_id,
            axis=1,
        ),
    )

    return reviews, source_rows


def build_sellers() -> tuple[pd.DataFrame, int]:
    sellers = read_csv(SOURCE_FILES["sellers"])
    source_rows = len(sellers)

    sellers = clean_string_columns(sellers)
    sellers = sellers.drop_duplicates().copy()

    sellers["seller_zip_code_prefix"] = pd.to_numeric(
        sellers["seller_zip_code_prefix"],
        errors="coerce",
    ).astype("Int64")

    sellers["seller_city"] = (
        sellers["seller_city"].str.lower()
    )

    sellers["seller_state"] = (
        sellers["seller_state"].str.upper()
    )

    return sellers, source_rows


def main() -> None:
    started_at = datetime.now(timezone.utc)

    print("Starting Silver-layer build...\n")

    build_steps = [
        (
            "silver_orders",
            build_orders,
            "Parsed timestamps and added delivery measures.",
        ),
        (
            "silver_order_items",
            build_order_items,
            "Standardised numeric fields and calculated item total.",
        ),
        (
            "silver_payments",
            build_payments,
            "Standardised payment numeric fields.",
        ),
        (
            "silver_customers",
            build_customers,
            "Standardised location fields and ZIP prefixes.",
        ),
        (
            "silver_customer_contact",
            build_customer_contact,
            "Standardised synthetic contact and consent fields.",
        ),
        (
            "silver_products",
            build_products,
            "Corrected source column-name spelling and numeric types.",
        ),
        (
            "silver_product_categories",
            build_product_categories,
            "Standardised category translation values.",
        ),
        (
            "silver_geolocation",
            build_geolocation,
            (
                "Removed exact duplicates and created one deterministic "
                "record per ZIP-code prefix."
            ),
        ),
        (
            "silver_reviews",
            build_reviews,
            (
                "Preserved review records and created deterministic "
                "review_record_id."
            ),
        ),
        (
            "silver_sellers",
            build_sellers,
            "Standardised seller location fields.",
        ),
    ]

    manifest_rows: list[dict[str, Any]] = []

    for dataset_name, build_function, notes in build_steps:
        dataframe, source_rows = build_function()

        manifest_row = write_silver_dataset(
            dataset_name=dataset_name,
            dataframe=dataframe,
            source_rows=source_rows,
            notes=notes,
        )

        manifest_rows.append(manifest_row)

        print(
            f"{dataset_name}: "
            f"{source_rows:,} source rows -> "
            f"{len(dataframe):,} Silver rows"
        )

    completed_at = datetime.now(timezone.utc)

    manifest = pd.DataFrame(manifest_rows)
    manifest.insert(
        0,
        "build_started_at",
        started_at.isoformat(),
    )
    manifest.insert(
        1,
        "build_completed_at",
        completed_at.isoformat(),
    )
    manifest.insert(
        2,
        "build_duration_seconds",
        round(
            (completed_at - started_at).total_seconds(),
            4,
        ),
    )

    manifest_path = (
        RESULTS_DIR / "silver_build_manifest.csv"
    )

    manifest.to_csv(
        manifest_path,
        index=False,
    )

    summary_path = RESULTS_DIR / "silver_build_summary.json"

    summary_path.write_text(
        json.dumps(
            {
                "status": "success",
                "build_started_at": started_at.isoformat(),
                "build_completed_at": completed_at.isoformat(),
                "build_duration_seconds": round(
                    (
                        completed_at
                        - started_at
                    ).total_seconds(),
                    4,
                ),
                "dataset_count": len(manifest_rows),
                "outputs": manifest_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    log_path = LOG_DIR / "silver_build.log"

    log_path.write_text(
        (
            "Silver-layer build completed successfully.\n"
            f"Started: {started_at.isoformat()}\n"
            f"Completed: {completed_at.isoformat()}\n"
            f"Datasets created: {len(manifest_rows)}\n"
            f"Manifest: {manifest_path}\n"
            f"Summary: {summary_path}\n"
        ),
        encoding="utf-8",
    )

    print("\nSilver-layer build completed successfully.")
    print(f"Manifest: {manifest_path}")
    print(f"Summary: {summary_path}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()