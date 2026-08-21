from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

COLLECTOR = (
    REPO_ROOT
    / "scripts"
    / "policy"
    / "collect_pre_gate_evidence.py"
)


SILVER_MODELS = [
    "silver_customer_contact",
    "silver_customers",
    "silver_geolocation",
    "silver_order_items",
    "silver_orders",
    "silver_payments",
    "silver_product_categories",
    "silver_products",
    "silver_reviews",
    "silver_sellers",
]

GOLD_INTERNAL = [
    "gold_customer_order_summary",
    "gold_daily_sales",
    "gold_product_category_revenue",
    "gold_sales_by_state",
]

GOLD_PUBLIC = [
    "gold_public_sales_dashboard",
]


def git(
    root: Path,
    *arguments: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return completed.stdout.strip()


def manifest_payload() -> dict:
    nodes = {}

    for name in SILVER_MODELS:
        unique_id = (
            f"model.thesis_pac_pipeline.{name}"
        )

        nodes[unique_id] = {
            "name": name,
            "resource_type": "model",
            "original_file_path": (
                f"models/silver/{name}.sql"
            ),
            "config": {
                "materialized": "table",
            },
            "tags": [
                "silver",
                "reference_parity",
            ],
            "depends_on": {
                "nodes": [],
            },
            "columns": {},
        }

    for name in GOLD_INTERNAL:
        unique_id = (
            f"model.thesis_pac_pipeline.{name}"
        )

        nodes[unique_id] = {
            "name": name,
            "resource_type": "model",
            "original_file_path": (
                f"models/gold/internal/{name}.sql"
            ),
            "config": {
                "materialized": "table",
            },
            "tags": [
                "gold",
                "internal",
            ],
            "depends_on": {
                "nodes": [],
            },
            "columns": {},
        }

    for name in GOLD_PUBLIC:
        unique_id = (
            f"model.thesis_pac_pipeline.{name}"
        )

        nodes[unique_id] = {
            "name": name,
            "resource_type": "model",
            "original_file_path": (
                f"models/gold/public/{name}.sql"
            ),
            "config": {
                "materialized": "table",
            },
            "tags": [
                "gold",
                "public",
                "public_safe",
            ],
            "depends_on": {
                "nodes": [],
            },
            "columns": {},
        }

    return {
        "metadata": {
            "project_name": "thesis_pac_pipeline",
            "dbt_version": "1.11.11",
            "adapter_type": "athena",
        },
        "nodes": nodes,
        "sources": {},
    }


def contract_sql(
    include_forbidden: bool = False,
) -> str:
    rows = []

    definitions = {
        "gold_customer_order_summary": [
            "customer_unique_id",
            "total_orders",
        ],
        "gold_daily_sales": [
            "order_date",
            "total_orders",
        ],
        "gold_product_category_revenue": [
            "product_category_name_english",
            "total_revenue",
        ],
        "gold_sales_by_state": [
            "customer_state",
            "total_revenue",
        ],
        "gold_public_sales_dashboard": [
            "order_date",
            "total_revenue",
        ],
    }

    if include_forbidden:
        definitions[
            "gold_public_sales_dashboard"
        ].append("synthetic_email")

    for model_name, columns in definitions.items():
        schema = (
            "gold_public"
            if model_name
            == "gold_public_sales_dashboard"
            else "gold_internal"
        )

        for ordinal, column in enumerate(
            columns,
            start=1,
        ):
            rows.append(
                "('%s', '%s', %d, '%s')"
                % (
                    schema,
                    model_name,
                    ordinal,
                    column,
                )
            )

    return (
        "values\n"
        + ",\n".join(rows)
        + "\n"
    )


PRIVACY_SQL = """
select column_name
from information_schema.columns
where lower(column_name) in (
  'customer_id',
  'customer_unique_id',
  'synthetic_email',
  'synthetic_phone'
)
or regexp_like(
  lower(column_name),
  'email|phone|address|zip_code|postal|consent'
)
"""


class CollectorTests(unittest.TestCase):
    def prepare_repository(
        self,
        root: Path,
    ) -> tuple[Path, Path, str]:
        git(root, "init", "-q")
        git(
            root,
            "config",
            "user.email",
            "collector@example.invalid",
        )
        git(
            root,
            "config",
            "user.name",
            "Collector Test",
        )
        git(
            root,
            "checkout",
            "-q",
            "-b",
            "test",
        )

        contract = (
            root
            / "transformations"
            / "dbt"
            / "tests"
            / "gold_contract_columns.sql"
        )

        privacy = (
            root
            / "transformations"
            / "dbt"
            / "tests"
            / "gold_public_privacy.sql"
        )

        models_root = (
            root
            / "transformations"
            / "dbt"
            / "models"
        )

        contract.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        models_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        contract.write_text(
            contract_sql(),
            encoding="utf-8",
        )

        privacy.write_text(
            PRIVACY_SQL,
            encoding="utf-8",
        )

        for name in SILVER_MODELS:
            target = (
                models_root
                / "silver"
                / f"{name}.sql"
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            target.write_text(
                "select 1\n",
                encoding="utf-8",
            )

        for name in GOLD_INTERNAL:
            target = (
                models_root
                / "gold"
                / "internal"
                / f"{name}.sql"
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            target.write_text(
                "select 1\n",
                encoding="utf-8",
            )

        public_target = (
            models_root
            / "gold"
            / "public"
            / "gold_public_sales_dashboard.sql"
        )

        public_target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        public_target.write_text(
            "select 1\n",
            encoding="utf-8",
        )

        git(root, "add", ".")
        git(
            root,
            "commit",
            "-q",
            "-m",
            "baseline",
        )

        base = git(
            root,
            "rev-parse",
            "HEAD",
        )

        return contract, privacy, base

    def run_collector(
        self,
        root: Path,
        contract: Path,
        privacy: Path,
        base: str,
    ) -> dict:
        manifest = root / "manifest.json"

        manifest.write_text(
            json.dumps(
                manifest_payload(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        output = root / "evidence.json"

        completed = subprocess.run(
            [
                sys.executable,
                str(COLLECTOR),
                "--repo-root",
                str(root),
                "--base-ref",
                base,
                "--manifest",
                str(manifest),
                "--contract-sql",
                str(contract),
                "--privacy-sql",
                str(privacy),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn(
            '"status": "PASS"',
            completed.stdout,
        )

        return json.loads(
            output.read_text(
                encoding="utf-8"
            )
        )

    def test_safe_baseline(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            contract, privacy, base = (
                self.prepare_repository(root)
            )

            evidence = self.run_collector(
                root,
                contract,
                privacy,
                base,
            )

            self.assertTrue(
                evidence["metadata"][
                    "required_fields_present"
                ]
            )

            self.assertEqual(
                evidence["metadata"][
                    "resource_count"
                ],
                15,
            )

            self.assertEqual(
                len(
                    evidence[
                        "schema_contract"
                    ][
                        "governed_models"
                    ]
                ),
                5,
            )

            self.assertEqual(
                evidence["privacy"][
                    "detected_forbidden_columns"
                ],
                [],
            )

            self.assertEqual(
                evidence["quality"]["status"],
                "NOT_EVALUATED",
            )

            self.assertEqual(
                evidence["freshness"]["status"],
                "NOT_EVALUATED",
            )

            self.assertEqual(
                evidence["runtime"][
                    "pipeline_status"
                ],
                "NOT_RUN",
            )

    def test_contract_and_privacy_drift_detected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            contract, privacy, base = (
                self.prepare_repository(root)
            )

            contract.write_text(
                contract_sql(
                    include_forbidden=True
                ),
                encoding="utf-8",
            )

            changed_model = (
                root
                / "transformations"
                / "dbt"
                / "models"
                / "silver"
                / "silver_orders.sql"
            )

            changed_model.write_text(
                "select 2\n",
                encoding="utf-8",
            )

            git(root, "add", ".")
            git(
                root,
                "commit",
                "-q",
                "-m",
                "unsafe candidate",
            )

            evidence = self.run_collector(
                root,
                contract,
                privacy,
                base,
            )

            public_contract = next(
                item
                for item in evidence[
                    "schema_contract"
                ][
                    "governed_models"
                ]
                if item["model"]
                == "gold_public_sales_dashboard"
            )

            self.assertIn(
                "synthetic_email",
                public_contract[
                    "unexpected_columns"
                ],
            )

            self.assertIn(
                "synthetic_email",
                evidence["privacy"][
                    "detected_forbidden_columns"
                ],
            )

            self.assertIn(
                "silver_orders",
                evidence["transformation"][
                    "changed_models"
                ],
            )


if __name__ == "__main__":
    unittest.main()
