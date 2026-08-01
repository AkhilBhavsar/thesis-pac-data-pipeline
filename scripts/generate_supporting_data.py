from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

BASE = Path(".")
GENERATED = BASE / "data" / "bronze" / "generated"
METADATA = BASE / "governance" / "metadata"
EXPERIMENTS = BASE / "experiments" / "results"

GENERATED.mkdir(parents=True, exist_ok=True)
METADATA.mkdir(parents=True, exist_ok=True)
EXPERIMENTS.mkdir(parents=True, exist_ok=True)

# -----------------------------
# 1. Dataset metadata registry
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
# 2. Freshness control table
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
# 3. Experiment tracking file
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
# 4. Governance contracts
# -----------------------------
# Authoritative dataset contracts are maintained as tracked YAML files
# under governance/contracts. This script must not generate or overwrite them.

print("Supporting data generated successfully.")
print(
    "Synthetic customer contact is managed by: "
    "scripts/bronze/build_synthetic_customer_contact.py"
)
print(f"Created: {METADATA / 'dataset_metadata.csv'}")
print(f"Created: {GENERATED / 'freshness_control.csv'}")
print(f"Created: {EXPERIMENTS / 'experiment_runs.csv'}")
print(
    "Governance contracts are maintained in: "
    "governance/contracts"
)
