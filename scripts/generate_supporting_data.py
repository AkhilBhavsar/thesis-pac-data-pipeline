from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

BASE = Path(".")
RAW = BASE / "data" / "bronze" / "raw" / "olist"
GENERATED = BASE / "data" / "bronze" / "generated"
METADATA = BASE / "governance" / "metadata"
CONTRACTS = BASE / "governance" / "contracts"
EXPERIMENTS = BASE / "experiments" / "results"

GENERATED.mkdir(parents=True, exist_ok=True)
METADATA.mkdir(parents=True, exist_ok=True)
CONTRACTS.mkdir(parents=True, exist_ok=True)
EXPERIMENTS.mkdir(parents=True, exist_ok=True)

customers_path = RAW / "olist_customers_dataset.csv"

if not customers_path.exists():
    raise FileNotFoundError(f"Missing file: {customers_path}")

customers = pd.read_csv(customers_path)

# -----------------------------
# 1. Synthetic customer contact extension
# -----------------------------
# This is NOT real PII. It is fake project data used to test PII policies safely.

contact = customers[["customer_id"]].drop_duplicates().copy()
contact["synthetic_email"] = contact["customer_id"].apply(
    lambda x: f"{str(x).lower()[:12]}@synthetic-example.com"
)
contact["synthetic_phone"] = [
    f"+353800{str(i).zfill(7)}" for i in range(1, len(contact) + 1)
]
contact["marketing_consent"] = np.random.choice(
    [True, False], size=len(contact), p=[0.75, 0.25]
)
contact["pii_classification"] = "PII"

contact.to_csv(GENERATED / "synthetic_customer_contact.csv", index=False)

# -----------------------------
# 2. Dataset metadata registry
# -----------------------------

metadata_rows = [
    {
        "dataset_name": "bronze_orders",
        "owner": "Data Platform Team",
        "classification": "Internal",
        "retention_days": 365,
        "destination_zone": "bronze/raw",
        "freshness_slo_hours": 24,
        "business_criticality": "High",
    },
    {
        "dataset_name": "bronze_customers",
        "owner": "Data Platform Team",
        "classification": "Confidential",
        "retention_days": 365,
        "destination_zone": "bronze/raw",
        "freshness_slo_hours": 24,
        "business_criticality": "High",
    },
    {
        "dataset_name": "silver_orders",
        "owner": "Data Platform Team",
        "classification": "Internal",
        "retention_days": 365,
        "destination_zone": "silver",
        "freshness_slo_hours": 24,
        "business_criticality": "High",
    },
    {
        "dataset_name": "silver_customers",
        "owner": "Data Platform Team",
        "classification": "Confidential",
        "retention_days": 365,
        "destination_zone": "silver",
        "freshness_slo_hours": 24,
        "business_criticality": "Medium",
    },
    {
        "dataset_name": "gold_daily_sales",
        "owner": "Analytics Team",
        "classification": "Internal",
        "retention_days": 365,
        "destination_zone": "gold/internal",
        "freshness_slo_hours": 24,
        "business_criticality": "High",
    },
    {
        "dataset_name": "gold_product_category_revenue",
        "owner": "Analytics Team",
        "classification": "Internal",
        "retention_days": 365,
        "destination_zone": "gold/internal",
        "freshness_slo_hours": 24,
        "business_criticality": "Medium",
    },
    {
        "dataset_name": "gold_customer_order_summary",
        "owner": "Analytics Team",
        "classification": "Confidential",
        "retention_days": 365,
        "destination_zone": "gold/internal",
        "freshness_slo_hours": 24,
        "business_criticality": "Medium",
    },
    {
        "dataset_name": "gold_public_sales_dashboard",
        "owner": "Analytics Team",
        "classification": "Public-Safe",
        "retention_days": 365,
        "destination_zone": "gold/public",
        "freshness_slo_hours": 24,
        "business_criticality": "High",
    },
]

metadata_df = pd.DataFrame(metadata_rows)
metadata_df.to_csv(METADATA / "dataset_metadata.csv", index=False)

# -----------------------------
# 3. Freshness control table
# -----------------------------

now = datetime.utcnow().replace(microsecond=0)
freshness_rows = []

for dataset in [
    "gold_daily_sales",
    "gold_product_category_revenue",
    "gold_customer_order_summary",
    "gold_public_sales_dashboard",
]:
    freshness_rows.append(
        {
            "dataset_name": dataset,
            "expected_publish_time": (now + timedelta(hours=24)).isoformat(),
            "actual_publish_time": now.isoformat(),
            "freshness_slo_hours": 24,
            "freshness_status": "PASS",
            "run_id": "baseline_run_001",
        }
    )

freshness_df = pd.DataFrame(freshness_rows)
freshness_df.to_csv(GENERATED / "freshness_control.csv", index=False)

# -----------------------------
# 4. Experiment tracking file
# -----------------------------

experiment_columns = [
    "run_id",
    "scenario_id",
    "condition",
    "start_time",
    "detection_time",
    "remediation_start_time",
    "remediation_end_time",
    "policy_decision",
    "remediation_action",
    "final_state",
    "notes",
]

pd.DataFrame(columns=experiment_columns).to_csv(
    EXPERIMENTS / "experiment_runs.csv", index=False
)

# -----------------------------
# 5. Dataset contracts
# -----------------------------

gold_public_contract = """dataset: gold_public_sales_dashboard
version: 1.0
owner: Analytics Team
classification: Public-Safe
freshness_slo_hours: 24
allowed_destinations:
  - gold/public
columns:
  order_date:
    type: date
    required: true
    pii: false
  customer_state:
    type: string
    required: true
    pii: false
  product_category_name_english:
    type: string
    required: true
    pii: false
  total_orders:
    type: integer
    required: true
    pii: false
  total_revenue:
    type: decimal
    required: true
    pii: false
forbidden_fields:
  - customer_id
  - customer_unique_id
  - synthetic_email
  - synthetic_phone
compatibility:
  allow_add_optional_column: true
  allow_remove_required_column: false
  allow_type_change_required_column: false
"""

gold_daily_sales_contract = """dataset: gold_daily_sales
version: 1.0
owner: Analytics Team
classification: Internal
freshness_slo_hours: 24
allowed_destinations:
  - gold/internal
columns:
  order_date:
    type: date
    required: true
    pii: false
  total_orders:
    type: integer
    required: true
    pii: false
  total_revenue:
    type: decimal
    required: true
    pii: false
  average_order_value:
    type: decimal
    required: true
    pii: false
compatibility:
  allow_add_optional_column: true
  allow_remove_required_column: false
  allow_type_change_required_column: false
"""

gold_customer_summary_contract = """dataset: gold_customer_order_summary
version: 1.0
owner: Analytics Team
classification: Confidential
freshness_slo_hours: 24
allowed_destinations:
  - gold/internal
columns:
  customer_id:
    type: string
    required: true
    pii: false
  customer_state:
    type: string
    required: true
    pii: false
  total_orders:
    type: integer
    required: true
    pii: false
  total_spend:
    type: decimal
    required: true
    pii: false
  first_order_date:
    type: date
    required: true
    pii: false
  last_order_date:
    type: date
    required: true
    pii: false
forbidden_destinations:
  - gold/public
compatibility:
  allow_add_optional_column: true
  allow_remove_required_column: false
  allow_type_change_required_column: false
"""

(CONTRACTS / "gold_public_sales_dashboard.yml").write_text(gold_public_contract)
(CONTRACTS / "gold_daily_sales.yml").write_text(gold_daily_sales_contract)
(CONTRACTS / "gold_customer_order_summary.yml").write_text(gold_customer_summary_contract)

print("Supporting data generated successfully.")
print(f"Created: {GENERATED / 'synthetic_customer_contact.csv'}")
print(f"Created: {METADATA / 'dataset_metadata.csv'}")
print(f"Created: {GENERATED / 'freshness_control.csv'}")
print(f"Created: {EXPERIMENTS / 'experiment_runs.csv'}")
print(f"Created contracts in: {CONTRACTS}")