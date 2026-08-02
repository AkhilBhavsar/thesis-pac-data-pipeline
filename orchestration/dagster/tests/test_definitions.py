from __future__ import annotations

import json
import unittest

import dagster as dg

from thesis_orchestration.assets import (
    thesis_dbt_assets,
)
from thesis_orchestration.definitions import defs
from thesis_orchestration.paths import (
    DBT_PROJECT_DIR,
    MANIFEST_PATH,
)


class DagsterDefinitionsTest(unittest.TestCase):
    def test_dbt_project_exists(self) -> None:
        self.assertTrue(
            (
                DBT_PROJECT_DIR
                / "dbt_project.yml"
            ).is_file()
        )

    def test_materialized_asset_count(self) -> None:
        self.assertEqual(
            len(thesis_dbt_assets.keys),
            15,
        )

    def test_manifest_inventory(self) -> None:
        payload = json.loads(
            MANIFEST_PATH.read_text(
                encoding="utf-8"
            )
        )

        models = [
            node
            for node in payload["nodes"].values()
            if node.get("resource_type") == "model"
        ]

        tests = [
            node
            for node in payload["nodes"].values()
            if node.get("resource_type") == "test"
        ]

        silver_models = [
            node
            for node in models
            if "silver" in set(
                node.get("tags") or []
            )
        ]

        gold_models = [
            node
            for node in models
            if "gold" in set(
                node.get("tags") or []
            )
        ]

        ephemeral_models = [
            node
            for node in models
            if (
                node.get("config", {}).get(
                    "materialized"
                )
                == "ephemeral"
            )
        ]

        self.assertEqual(len(models), 17)
        self.assertEqual(len(silver_models), 10)
        self.assertEqual(len(gold_models), 5)
        self.assertEqual(len(ephemeral_models), 2)
        self.assertEqual(len(tests), 41)

        self.assertEqual(
            len(payload.get("sources", {})),
            10,
        )

    def test_definitions_are_loadable(self) -> None:
        dg.Definitions.validate_loadable(defs)

    def test_expected_jobs_exist(self) -> None:
        expected_jobs = {
            "silver_dbt_job",
            "gold_dbt_job",
            "bronze_silver_gold_job",
        }

        for job_name in expected_jobs:
            job = defs.resolve_job_def(job_name)

            self.assertEqual(
                job.name,
                job_name,
            )


if __name__ == "__main__":
    unittest.main()
