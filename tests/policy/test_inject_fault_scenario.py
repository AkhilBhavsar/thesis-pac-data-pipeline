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


class PiiExposureInjectorTest(
    unittest.TestCase
):
    def test_pii_exposure_adds_forbidden_public_column(
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

        privacy_file = (
            REPO_ROOT
            / "transformations"
            / "dbt"
            / "tests"
            / "gold_public_privacy.sql"
        )

        forbidden, pattern = (
            collector.parse_privacy_rule(
                privacy_file.read_text(
                    encoding="utf-8"
                )
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
                    "pii_exposure",
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

            stdout_payload = json.loads(
                completed.stdout
            )

            self.assertEqual(
                stdout_payload[
                    "scenario_id"
                ],
                "pii_exposure",
            )

            self.assertEqual(
                stdout_payload[
                    "fault_operation"
                ],
                "add_forbidden_public_contract_column",
            )

            self.assertEqual(
                stdout_payload[
                    "fault_column"
                ],
                "synthetic_email",
            )

            self.assertNotIn(
                "removed_column",
                stdout_payload,
            )

            current = (
                collector.parse_contract(
                    target.read_text(
                        encoding="utf-8"
                    )
                )
            )

            model = (
                "gold_public_sales_dashboard"
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
                8,
            )

            self.assertEqual(
                len(current_columns),
                9,
            )

            self.assertEqual(
                missing,
                [],
            )

            self.assertEqual(
                unexpected,
                [
                    "synthetic_email",
                ],
            )

            self.assertEqual(
                current_columns[-1],
                "synthetic_email",
            )

            self.assertIn(
                "synthetic_email",
                forbidden,
            )

            import re

            compiled = re.compile(
                pattern,
                re.IGNORECASE,
            )

            detected = sorted({
                column
                for column
                in current_columns
                if (
                    column.lower()
                    in {
                        item.lower()
                        for item in forbidden
                    }
                    or compiled.search(
                        column.lower()
                    )
                )
            })

            self.assertEqual(
                detected,
                [
                    "synthetic_email",
                ],
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
                "pii_exposure",
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
                "synthetic_email",
            )

            self.assertEqual(
                payload[
                    "expected_effect"
                ][
                    "primary_policy_id"
                ],
                "PAC-PRIVACY-001",
            )

            self.assertEqual(
                payload[
                    "expected_effect"
                ][
                    "defence_in_depth_policy_id"
                ],
                "PAC-SCHEMA-001",
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

    def test_pii_reinjection_is_rejected(
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

            command = [
                sys.executable,
                str(INJECTOR),
                "--scenario",
                "pii_exposure",
                "--repo-root",
                str(temp_root),
                "--evidence-dir",
                str(evidence),
            ]

            first = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                first.returncode,
                0,
            )

            second = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(
                second.returncode,
                0,
            )

            self.assertIn(
                "already appears to be injected",
                second.stderr,
            )


class PolicyFalsePositiveInjectorTest(
    unittest.TestCase
):
    def test_safe_additive_internal_contract_change(
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

        baseline_source_bytes = (
            SOURCE_CONTRACT
            .read_bytes()
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
                    "policy_false_positive",
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
                12,
            )

            self.assertEqual(
                missing,
                [],
            )

            self.assertEqual(
                unexpected,
                [
                    "synthetic_optional_note",
                ],
            )

            self.assertEqual(
                current_columns[-1],
                "synthetic_optional_note",
            )

            stdout_payload = json.loads(
                completed.stdout
            )

            self.assertEqual(
                stdout_payload[
                    "status"
                ],
                "PASS",
            )

            self.assertEqual(
                stdout_payload[
                    "scenario_id"
                ],
                "policy_false_positive",
            )

            self.assertEqual(
                stdout_payload[
                    "target_model"
                ],
                model,
            )

            self.assertEqual(
                stdout_payload[
                    "fault_column"
                ],
                "synthetic_optional_note",
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
                payload[
                    "ground_truth"
                ][
                    "classification"
                ],
                "SAFE",
            )

            self.assertEqual(
                payload[
                    "ground_truth"
                ][
                    "expected_decision"
                ],
                "ALLOW",
            )

            self.assertEqual(
                payload[
                    "ground_truth"
                ][
                    "change_type"
                ],
                (
                    "additive_optional_internal_"
                    "contract_column"
                ),
            )

            self.assertEqual(
                payload[
                    "ground_truth"
                ][
                    "target_exposure"
                ],
                "internal",
            )

            self.assertEqual(
                payload[
                    "ground_truth"
                ][
                    "required_columns_removed"
                ],
                0,
            )

            self.assertEqual(
                payload[
                    "ground_truth"
                ][
                    "incompatible_type_changes"
                ],
                0,
            )

            self.assertFalse(
                payload[
                    "ground_truth"
                ][
                    "public_output_changed"
                ]
            )

            self.assertFalse(
                payload[
                    "ground_truth"
                ][
                    "sensitive_field_added"
                ]
            )

            self.assertTrue(
                payload[
                    "ground_truth"
                ][
                    "existing_required_contract_retained"
                ]
            )

            collector_effect = payload[
                "expected_collector_effect"
            ]

            self.assertEqual(
                collector_effect[
                    "expected_column_count"
                ],
                11,
            )

            self.assertEqual(
                collector_effect[
                    "actual_column_count"
                ],
                12,
            )

            self.assertEqual(
                collector_effect[
                    "missing_columns"
                ],
                [],
            )

            self.assertEqual(
                collector_effect[
                    "unexpected_columns"
                ],
                [
                    "synthetic_optional_note",
                ],
            )

            self.assertEqual(
                collector_effect[
                    "incompatible_type_changes"
                ],
                [],
            )

            self.assertEqual(
                collector_effect[
                    "exposure"
                ],
                "internal",
            )

            policy_effect = payload[
                "expected_policy_effect"
            ]

            self.assertEqual(
                policy_effect[
                    "primary_policy_id"
                ],
                "PAC-SCHEMA-001",
            )

            self.assertEqual(
                policy_effect[
                    "release_policy_id"
                ],
                "PAC-RELEASE-001",
            )

            self.assertEqual(
                policy_effect[
                    "decision"
                ],
                "DENY",
            )

            self.assertEqual(
                policy_effect[
                    "classification_if_observed"
                ],
                "FALSE_POSITIVE",
            )

            self.assertTrue(
                policy_effect[
                    "blocked_safe_change"
                ]
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

            self.assertFalse(
                payload[
                    "safety"
                ][
                    "public_gold_mutated"
                ]
            )

            self.assertEqual(
                SOURCE_CONTRACT.read_bytes(),
                baseline_source_bytes,
            )

    def test_safe_additive_change_reinjection_is_rejected(
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

            command = [
                sys.executable,
                str(INJECTOR),
                "--scenario",
                "policy_false_positive",
                "--repo-root",
                str(temp_root),
                "--evidence-dir",
                str(
                    temp_root
                    / "evidence"
                ),
            ]

            first = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                first.returncode,
                0,
                msg=(
                    first.stdout
                    + first.stderr
                ),
            )

            first_bytes = (
                target.read_bytes()
            )

            second = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                second.returncode,
                1,
            )

            self.assertIn(
                (
                    "False-positive additive contract "
                    "column already appears injected."
                ),
                second.stderr,
            )

            self.assertEqual(
                target.read_bytes(),
                first_bytes,
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
