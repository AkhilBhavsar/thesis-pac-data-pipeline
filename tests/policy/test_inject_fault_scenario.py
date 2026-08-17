#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

INJECTOR = (
    REPO_ROOT
    / "scripts"
    / "experiments"
    / "inject_fault_scenario.py"
)

COLLECTOR = (
    REPO_ROOT
    / "scripts"
    / "policy"
    / "collect_pre_gate_evidence.py"
)

CONTRACT_RELATIVE = Path(
    "transformations/dbt/tests/"
    "gold_contract_columns.sql"
)

SOURCE_CONTRACT = (
    REPO_ROOT
    / CONTRACT_RELATIVE
)


def load_collector_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "collect_pre_gate_evidence",
            COLLECTOR,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Unable to load collector."
        )

    module = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


class SchemaBreakInjectorTest(
    unittest.TestCase
):
    def test_schema_break_removes_only_last_required_column(
        self,
    ) -> None:
        collector = (
            load_collector_module()
        )

        baseline_text = (
            SOURCE_CONTRACT
            .read_text(
                encoding="utf-8"
            )
        )

        baseline = (
            collector.parse_contract(
                baseline_text
            )
        )

        with tempfile.TemporaryDirectory() as raw:
            temp_root = Path(raw)

            target = (
                temp_root
                / CONTRACT_RELATIVE
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                SOURCE_CONTRACT,
                target,
            )

            evidence = (
                temp_root
                / "evidence"
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "schema_break",
                    "--repo-root",
                    str(temp_root),
                    "--evidence-dir",
                    str(evidence),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                completed.returncode,
                0,
                msg=(
                    completed.stdout
                    + completed.stderr
                ),
            )

            current_text = (
                target.read_text(
                    encoding="utf-8"
                )
            )

            current = (
                collector.parse_contract(
                    current_text
                )
            )

            model = (
                "gold_customer_order_summary"
            )

            expected_columns = (
                collector.contract_columns(
                    baseline[model]
                )
            )

            current_columns = (
                collector.contract_columns(
                    current[model]
                )
            )

            missing, unexpected = (
                collector.contract_differences(
                    expected_columns,
                    current_columns,
                )
            )

            self.assertEqual(
                len(expected_columns),
                11,
            )

            self.assertEqual(
                len(current_columns),
                10,
            )

            self.assertEqual(
                missing,
                [
                    "average_order_value",
                ],
            )

            self.assertEqual(
                unexpected,
                [],
            )

            self.assertEqual(
                current_columns,
                expected_columns[:-1],
            )

            payload = json.loads(
                (
                    evidence
                    / "fault-injection.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                payload["scenario_id"],
                "schema_break",
            )

            self.assertEqual(
                payload["target_model"],
                model,
            )

            self.assertEqual(
                payload[
                    "fault"
                ][
                    "column"
                ],
                "average_order_value",
            )

            self.assertFalse(
                payload[
                    "safety"
                ][
                    "canonical_data_mutated"
                ]
            )

            self.assertFalse(
                payload[
                    "safety"
                ][
                    "aws_mutation_performed"
                ]
            )

            self.assertTrue(
                (
                    evidence
                    / "fault-injection.patch"
                ).is_file()
            )

    def test_reinjection_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp_root = Path(raw)

            target = (
                temp_root
                / CONTRACT_RELATIVE
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                SOURCE_CONTRACT,
                target,
            )

            evidence = (
                temp_root
                / "evidence"
            )

            first = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "schema_break",
                    "--repo-root",
                    str(temp_root),
                    "--evidence-dir",
                    str(evidence),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                first.returncode,
                0,
            )

            second = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "schema_break",
                    "--repo-root",
                    str(temp_root),
                    "--evidence-dir",
                    str(evidence),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(
                second.returncode,
                0,
            )

            self.assertIn(
                "Expected exactly one "
                "schema-break target tuple",
                second.stderr,
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
