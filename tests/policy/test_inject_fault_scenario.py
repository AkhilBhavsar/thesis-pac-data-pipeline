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
    def test_safe_nullable_additive_internal_change(
        self,
    ) -> None:
        collector = (
            load_collector_module()
        )

        model_relative = Path(
            "transformations/dbt/models/"
            "gold/internal/"
            "gold_customer_order_summary.sql"
        )

        source_model = (
            REPO_ROOT
            / model_relative
        )

        baseline_contract_bytes = (
            SOURCE_CONTRACT.read_bytes()
        )

        baseline_model_bytes = (
            source_model.read_bytes()
        )

        baseline_contract_text = (
            baseline_contract_bytes.decode(
                "utf-8"
            )
        )

        baseline_model_text = (
            baseline_model_bytes.decode(
                "utf-8"
            )
        )

        baseline_contract = (
            collector.parse_contract(
                baseline_contract_text
            )
        )

        with tempfile.TemporaryDirectory() as raw:
            temp_root = Path(raw)

            target_contract = (
                temp_root
                / CONTRACT_RELATIVE
            )

            target_model = (
                temp_root
                / model_relative
            )

            target_contract.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            target_model.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                SOURCE_CONTRACT,
                target_contract,
            )

            shutil.copy2(
                source_model,
                target_model,
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

            current_contract_text = (
                target_contract.read_text(
                    encoding="utf-8"
                )
            )

            current_model_text = (
                target_model.read_text(
                    encoding="utf-8"
                )
            )

            current_contract = (
                collector.parse_contract(
                    current_contract_text
                )
            )

            model = (
                "gold_customer_order_summary"
            )

            expected_columns = (
                collector.contract_columns(
                    baseline_contract[
                        model
                    ]
                )
            )

            current_columns = (
                collector.contract_columns(
                    current_contract[
                        model
                    ]
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

            expected_model_text = (
                baseline_model_text.replace(
                    (
                        "    ) as average_order_value\n"
                        "\n"
                        "from customer_totals as totals"
                    ),
                    (
                        "    ) as average_order_value,\n"
                        "\n"
                        "    cast(\n"
                        "        null as varchar\n"
                        "    ) as synthetic_optional_note\n"
                        "\n"
                        "from customer_totals as totals"
                    ),
                    1,
                )
            )

            self.assertEqual(
                current_model_text,
                expected_model_text,
            )

            self.assertEqual(
                current_model_text.count(
                    "synthetic_optional_note"
                ),
                1,
            )

            self.assertIn(
                "cast(\n"
                "        null as varchar\n"
                "    ) as synthetic_optional_note",
                current_model_text,
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

            payload = json.loads(
                (
                    evidence
                    / "fault-injection.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            ground_truth = payload[
                "ground_truth"
            ]

            self.assertEqual(
                ground_truth[
                    "classification"
                ],
                "SAFE",
            )

            self.assertEqual(
                ground_truth[
                    "expected_decision"
                ],
                "ALLOW",
            )

            self.assertEqual(
                ground_truth[
                    "compatibility_rule"
                ],
                (
                    "nullable_additive_internal_"
                    "column_is_backward_compatible"
                ),
            )

            self.assertEqual(
                ground_truth[
                    "target_exposure"
                ],
                "internal",
            )

            self.assertEqual(
                ground_truth[
                    "required_columns_removed"
                ],
                0,
            )

            self.assertEqual(
                ground_truth[
                    "existing_column_types_changed"
                ],
                0,
            )

            self.assertTrue(
                ground_truth[
                    "existing_required_columns_retained"
                ]
            )

            self.assertTrue(
                ground_truth[
                    "new_column_nullable"
                ]
            )

            self.assertEqual(
                ground_truth[
                    "new_column_value_semantics"
                ],
                "NULL",
            )

            self.assertTrue(
                ground_truth[
                    "model_contract_aligned"
                ]
            )

            self.assertFalse(
                ground_truth[
                    "public_output_changed"
                ]
            )

            self.assertFalse(
                ground_truth[
                    "sensitive_field_added"
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

            patch = (
                evidence
                / "fault-injection.patch"
            ).read_text(
                encoding="utf-8"
            )

            self.assertIn(
                str(CONTRACT_RELATIVE),
                patch,
            )

            self.assertIn(
                str(model_relative),
                patch,
            )

            self.assertEqual(
                SOURCE_CONTRACT.read_bytes(),
                baseline_contract_bytes,
            )

            self.assertEqual(
                source_model.read_bytes(),
                baseline_model_bytes,
            )

    def test_safe_additive_change_reinjection_is_rejected(
        self,
    ) -> None:
        model_relative = Path(
            "transformations/dbt/models/"
            "gold/internal/"
            "gold_customer_order_summary.sql"
        )

        source_model = (
            REPO_ROOT
            / model_relative
        )

        with tempfile.TemporaryDirectory() as raw:
            temp_root = Path(raw)

            target_contract = (
                temp_root
                / CONTRACT_RELATIVE
            )

            target_model = (
                temp_root
                / model_relative
            )

            target_contract.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            target_model.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                SOURCE_CONTRACT,
                target_contract,
            )

            shutil.copy2(
                source_model,
                target_model,
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

            contract_after_first = (
                target_contract.read_bytes()
            )

            model_after_first = (
                target_model.read_bytes()
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
                    "False-positive additive change "
                    "already appears injected."
                ),
                second.stderr,
            )

            self.assertEqual(
                target_contract.read_bytes(),
                contract_after_first,
            )

            self.assertEqual(
                target_model.read_bytes(),
                model_after_first,
            )




if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
