from __future__ import annotations

import hashlib
import json
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

GOLD_INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
GOLD_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


SILVER_FILES = {
    "orders": SILVER_DIR / "silver_orders.csv",
    "order_items": SILVER_DIR / "silver_order_items.csv",
    "customers": SILVER_DIR / "silver_customers.csv",
    "products": SILVER_DIR / "silver_products.csv",
    "product_categories": (
        SILVER_DIR / "silver_product_categories.csv"
    ),
}


def require_file(path: Path) -> None:
    """Raise a clear error when a required Silver dataset is missing."""
    if not path.exists():
        raise FileNotFoundError(
            f"Required Silver dataset not found: {path}"
        )


def read_silver(path: Path) -> pd.DataFrame:
    """Read a Silver CSV using consistent settings."""
    require_file(path)

    return pd.read_csv(
        path,
        low_memory=False,
    )


def representative_mode(series: pd.Series) -> Any:
    """
    Return a deterministic representative value.

    When several values have the same frequency, the
    alphabetically first value is selected.
    """
    values = series.dropna().astype("string")

    if values.empty:
        return "unknown"

    counts = values.value_counts()
    maximum_count = counts.max()

    candidates = sorted(
        counts[counts == maximum_count]
        .index
        .astype(str)
    )

    return candidates[0]


def dataframe_hash(dataframe: pd.DataFrame) -> str:
    """Generate a deterministic SHA-256 hash for a dataframe."""
    hashed_values = pd.util.hash_pandas_object(
        dataframe,
        index=True,
    ).values

    return hashlib.sha256(
        hashed_values.tobytes()
    ).hexdigest()


def round_numeric_columns(
    dataframe: pd.DataFrame,
    decimal_places: int = 2,
) -> pd.DataFrame:
    """Round floating-point metrics consistently."""
    rounded = dataframe.copy()

    numeric_columns = rounded.select_dtypes(
        include=["number"]
    ).columns

    rounded[numeric_columns] = rounded[
        numeric_columns
    ].round(decimal_places)

    return rounded


def safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    """Calculate a ratio while avoiding division by zero."""
    denominator = denominator.replace(0, pd.NA)

    return (
        numerator.div(denominator)
        .fillna(0)
    )


def prepare_gold_foundation() -> tuple[
    dict[str, pd.DataFrame],
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Load Silver datasets and build common Gold foundations.

    Returns:
        input_datasets:
            Dictionary containing all loaded Silver datasets.
        order_financials:
            One row per delivered order.
        item_enriched:
            One row per delivered order item with customer,
            state and category attributes.
    """
    orders = read_silver(SILVER_FILES["orders"])
    order_items = read_silver(SILVER_FILES["order_items"])
    customers = read_silver(SILVER_FILES["customers"])
    products = read_silver(SILVER_FILES["products"])
    product_categories = read_silver(
        SILVER_FILES["product_categories"]
    )

    input_datasets = {
        "silver_orders": orders,
        "silver_order_items": order_items,
        "silver_customers": customers,
        "silver_products": products,
        "silver_product_categories": product_categories,
    }

    orders["order_purchase_timestamp"] = pd.to_datetime(
        orders["order_purchase_timestamp"],
        errors="coerce",
        utc=True,
    )

    orders["order_date"] = (
        orders["order_purchase_timestamp"]
        .dt.strftime("%Y-%m-%d")
    )

    orders["order_status"] = (
        orders["order_status"]
        .astype("string")
        .str.lower()
    )

    delivered_orders = orders[
        (orders["order_status"] == "delivered")
        & orders["order_date"].notna()
    ].copy()

    delivered_orders = delivered_orders[
        [
            "order_id",
            "customer_id",
            "order_date",
        ]
    ]

    customers["customer_state"] = (
        customers["customer_state"]
        .astype("string")
        .str.upper()
        .fillna("UNKNOWN")
    )

    products["product_category_name"] = (
        products["product_category_name"]
        .astype("string")
        .str.lower()
    )

    product_categories[
        "product_category_name"
    ] = (
        product_categories["product_category_name"]
        .astype("string")
        .str.lower()
    )

    product_categories[
        "product_category_name_english"
    ] = (
        product_categories[
            "product_category_name_english"
        ]
        .astype("string")
        .str.lower()
    )

    item_enriched = (
        order_items
        .merge(
            delivered_orders,
            on="order_id",
            how="inner",
            validate="many_to_one",
        )
        .merge(
            customers[
                [
                    "customer_id",
                    "customer_unique_id",
                    "customer_state",
                ]
            ],
            on="customer_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            products[
                [
                    "product_id",
                    "product_category_name",
                ]
            ],
            on="product_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            product_categories,
            on="product_category_name",
            how="left",
            validate="many_to_one",
        )
    )

    item_enriched["customer_state"] = (
        item_enriched["customer_state"]
        .fillna("UNKNOWN")
    )

    item_enriched[
        "product_category_name_english"
    ] = (
        item_enriched[
            "product_category_name_english"
        ]
        .fillna("unknown")
    )

    numeric_columns = [
        "price",
        "freight_value",
        "item_total_value",
    ]

    for column in numeric_columns:
        item_enriched[column] = pd.to_numeric(
            item_enriched[column],
            errors="coerce",
        ).fillna(0)

    order_financials = (
        item_enriched
        .groupby(
            [
                "order_id",
                "customer_id",
                "customer_unique_id",
                "customer_state",
                "order_date",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            total_items=(
                "order_item_id",
                "count",
            ),
            distinct_products=(
                "product_id",
                "nunique",
            ),
            product_revenue=(
                "price",
                "sum",
            ),
            freight_revenue=(
                "freight_value",
                "sum",
            ),
            total_revenue=(
                "item_total_value",
                "sum",
            ),
        )
    )

    order_financials = round_numeric_columns(
        order_financials
    )

    return (
        input_datasets,
        order_financials,
        item_enriched,
    )


def build_gold_daily_sales(
    order_financials: pd.DataFrame,
) -> pd.DataFrame:
    daily = (
        order_financials
        .groupby(
            "order_date",
            as_index=False,
        )
        .agg(
            total_orders=(
                "order_id",
                "nunique",
            ),
            unique_customers=(
                "customer_unique_id",
                "nunique",
            ),
            units_sold=(
                "total_items",
                "sum",
            ),
            product_revenue=(
                "product_revenue",
                "sum",
            ),
            freight_revenue=(
                "freight_revenue",
                "sum",
            ),
            total_revenue=(
                "total_revenue",
                "sum",
            ),
        )
    )

    daily["average_order_value"] = safe_ratio(
        daily["total_revenue"],
        daily["total_orders"],
    )

    daily["average_freight_value"] = safe_ratio(
        daily["freight_revenue"],
        daily["total_orders"],
    )

    daily = round_numeric_columns(daily)

    return daily.sort_values(
        "order_date"
    ).reset_index(drop=True)


def build_gold_sales_by_state(
    order_financials: pd.DataFrame,
) -> pd.DataFrame:
    state_sales = (
        order_financials
        .groupby(
            "customer_state",
            as_index=False,
        )
        .agg(
            total_orders=(
                "order_id",
                "nunique",
            ),
            unique_customers=(
                "customer_unique_id",
                "nunique",
            ),
            units_sold=(
                "total_items",
                "sum",
            ),
            product_revenue=(
                "product_revenue",
                "sum",
            ),
            freight_revenue=(
                "freight_revenue",
                "sum",
            ),
            total_revenue=(
                "total_revenue",
                "sum",
            ),
        )
    )

    state_sales["average_order_value"] = safe_ratio(
        state_sales["total_revenue"],
        state_sales["total_orders"],
    )

    state_sales = round_numeric_columns(
        state_sales
    )

    return state_sales.sort_values(
        [
            "total_revenue",
            "customer_state",
        ],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_gold_product_category_revenue(
    item_enriched: pd.DataFrame,
) -> pd.DataFrame:
    category_revenue = (
        item_enriched
        .groupby(
            "product_category_name_english",
            as_index=False,
        )
        .agg(
            total_orders=(
                "order_id",
                "nunique",
            ),
            unique_customers=(
                "customer_unique_id",
                "nunique",
            ),
            units_sold=(
                "order_item_id",
                "count",
            ),
            product_revenue=(
                "price",
                "sum",
            ),
            freight_revenue=(
                "freight_value",
                "sum",
            ),
            total_revenue=(
                "item_total_value",
                "sum",
            ),
            average_item_price=(
                "price",
                "mean",
            ),
        )
    )

    total_revenue_all_categories = (
        category_revenue["total_revenue"].sum()
    )

    if total_revenue_all_categories == 0:
        category_revenue["revenue_share_pct"] = 0
    else:
        category_revenue["revenue_share_pct"] = (
            category_revenue["total_revenue"]
            .div(total_revenue_all_categories)
            .mul(100)
        )

    category_revenue = round_numeric_columns(
        category_revenue
    )

    return category_revenue.sort_values(
        [
            "total_revenue",
            "product_category_name_english",
        ],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_gold_customer_order_summary(
    item_enriched: pd.DataFrame,
) -> pd.DataFrame:
    customer_summary = (
        item_enriched
        .groupby(
            "customer_unique_id",
            as_index=False,
            dropna=False,
        )
        .agg(
            customer_state=(
                "customer_state",
                representative_mode,
            ),
            first_order_date=(
                "order_date",
                "min",
            ),
            latest_order_date=(
                "order_date",
                "max",
            ),
            total_orders=(
                "order_id",
                "nunique",
            ),
            total_items=(
                "order_item_id",
                "count",
            ),
            distinct_products=(
                "product_id",
                "nunique",
            ),
            product_revenue=(
                "price",
                "sum",
            ),
            freight_revenue=(
                "freight_value",
                "sum",
            ),
            total_spend=(
                "item_total_value",
                "sum",
            ),
        )
    )

    customer_summary["average_order_value"] = safe_ratio(
        customer_summary["total_spend"],
        customer_summary["total_orders"],
    )

    customer_summary = round_numeric_columns(
        customer_summary
    )

    return customer_summary.sort_values(
        "customer_unique_id"
    ).reset_index(drop=True)


def build_gold_public_sales_dashboard(
    item_enriched: pd.DataFrame,
) -> pd.DataFrame:
    public_dashboard = (
        item_enriched
        .groupby(
            [
                "order_date",
                "customer_state",
                "product_category_name_english",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            total_orders=(
                "order_id",
                "nunique",
            ),
            units_sold=(
                "order_item_id",
                "count",
            ),
            product_revenue=(
                "price",
                "sum",
            ),
            freight_revenue=(
                "freight_value",
                "sum",
            ),
            total_revenue=(
                "item_total_value",
                "sum",
            ),
        )
    )

    public_dashboard = round_numeric_columns(
        public_dashboard
    )

    allowed_public_columns = [
        "order_date",
        "customer_state",
        "product_category_name_english",
        "total_orders",
        "units_sold",
        "product_revenue",
        "freight_revenue",
        "total_revenue",
    ]

    public_dashboard = public_dashboard[
        allowed_public_columns
    ]

    return public_dashboard.sort_values(
        [
            "order_date",
            "customer_state",
            "product_category_name_english",
        ]
    ).reset_index(drop=True)


def write_gold_dataset(
    dataset_name: str,
    dataframe: pd.DataFrame,
    zone: str,
    input_row_counts: dict[str, int],
    notes: str,
) -> dict[str, Any]:
    """Write a Gold dataset and return manifest evidence."""
    if zone == "internal":
        output_directory = GOLD_INTERNAL_DIR
    elif zone == "public":
        output_directory = GOLD_PUBLIC_DIR
    else:
        raise ValueError(
            f"Unsupported Gold zone: {zone}"
        )

    output_path = (
        output_directory / f"{dataset_name}.csv"
    )

    dataframe.to_csv(
        output_path,
        index=False,
    )

    return {
        "dataset": dataset_name,
        "zone": zone,
        "output_path": str(
            output_path.relative_to(PROJECT_ROOT)
        ),
        "row_count": len(dataframe),
        "column_count": len(dataframe.columns),
        "full_duplicate_rows": int(
            dataframe.duplicated().sum()
        ),
        "dataset_hash_sha256": dataframe_hash(
            dataframe
        ),
        "input_row_counts_json": json.dumps(
            input_row_counts,
            sort_keys=True,
        ),
        "notes": notes,
    }


def main() -> None:
    started_at = datetime.now(timezone.utc)

    print("Starting Gold-layer build...\n")

    (
        input_datasets,
        order_financials,
        item_enriched,
    ) = prepare_gold_foundation()

    input_row_counts = {
        name: len(dataframe)
        for name, dataframe in input_datasets.items()
    }

    gold_outputs = [
        (
            "gold_daily_sales",
            "internal",
            build_gold_daily_sales(
                order_financials
            ),
            (
                "Daily delivered-order sales metrics with "
                "order, customer, item and revenue measures."
            ),
        ),
        (
            "gold_sales_by_state",
            "internal",
            build_gold_sales_by_state(
                order_financials
            ),
            (
                "Delivered-order sales aggregated by "
                "customer state."
            ),
        ),
        (
            "gold_product_category_revenue",
            "internal",
            build_gold_product_category_revenue(
                item_enriched
            ),
            (
                "Delivered-item revenue and contribution "
                "metrics by translated product category."
            ),
        ),
        (
            "gold_customer_order_summary",
            "internal",
            build_gold_customer_order_summary(
                item_enriched
            ),
            (
                "Customer-level delivered-order history "
                "and lifetime-spend summary."
            ),
        ),
        (
            "gold_public_sales_dashboard",
            "public",
            build_gold_public_sales_dashboard(
                item_enriched
            ),
            (
                "Public-safe aggregate sales dataset with "
                "no customer identifiers or contact fields."
            ),
        ),
    ]

    manifest_rows: list[dict[str, Any]] = []

    for (
        dataset_name,
        zone,
        dataframe,
        notes,
    ) in gold_outputs:
        manifest_row = write_gold_dataset(
            dataset_name=dataset_name,
            dataframe=dataframe,
            zone=zone,
            input_row_counts=input_row_counts,
            notes=notes,
        )

        manifest_rows.append(manifest_row)

        print(
            f"{dataset_name}: "
            f"{len(dataframe):,} rows "
            f"written to Gold {zone}"
        )

    completed_at = datetime.now(timezone.utc)

    duration_seconds = round(
        (
            completed_at - started_at
        ).total_seconds(),
        4,
    )

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
        duration_seconds,
    )

    manifest_path = (
        RESULTS_DIR / "gold_build_manifest.csv"
    )

    manifest.to_csv(
        manifest_path,
        index=False,
    )

    summary = {
        "status": "success",
        "build_started_at": started_at.isoformat(),
        "build_completed_at": completed_at.isoformat(),
        "build_duration_seconds": duration_seconds,
        "delivered_order_count": int(
            order_financials["order_id"].nunique()
        ),
        "delivered_item_count": int(
            len(item_enriched)
        ),
        "dataset_count": len(manifest_rows),
        "outputs": manifest_rows,
    }

    summary_path = (
        RESULTS_DIR / "gold_build_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    log_path = LOG_DIR / "gold_build.log"

    log_path.write_text(
        (
            "Gold-layer build completed successfully.\n"
            f"Started: {started_at.isoformat()}\n"
            f"Completed: {completed_at.isoformat()}\n"
            f"Duration seconds: {duration_seconds}\n"
            f"Delivered orders: "
            f"{summary['delivered_order_count']}\n"
            f"Delivered items: "
            f"{summary['delivered_item_count']}\n"
            f"Gold datasets created: "
            f"{len(manifest_rows)}\n"
            f"Manifest: {manifest_path}\n"
            f"Summary: {summary_path}\n"
        ),
        encoding="utf-8",
    )

    print("\nGold-layer build completed successfully.")
    print(
        "Delivered orders used: "
        f"{summary['delivered_order_count']:,}"
    )
    print(
        "Delivered items used: "
        f"{summary['delivered_item_count']:,}"
    )
    print(f"Manifest: {manifest_path}")
    print(f"Summary: {summary_path}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()