#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
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
    / "inject_post_fault_scenario.py"
)

CSV_TEXT = """dataset_name,expected_publish_time,actual_publish_time,freshness_slo_hours,freshness_status,run_id
gold_daily_sales,2026-07-06T23:58:01,2026-07-05T23:58:01,24,PASS,baseline_run_001
gold_public_sales_dashboard,2026-07-06T23:58:01,2026-07-05T23:58:01,24,PASS,baseline_run_001
"""


def observed_age(
    row: dict[str, str],
) -> float:
    expected = datetime.fromisoformat(
        row[
            "expected_publish_time"
        ]
    )

    actual = datetime.fromisoformat(
        row[
            "actual_publish_time"
        ]
    )

    return max(
        0.0,
        (
            expected
            - actual
        ).total_seconds(),
    )


class FreshnessBreachInjectorTest(
    unittest.TestCase
):
    def test_breach_uses_copy_and_crosses_threshold(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            source = root / "source.csv"
            output = root / "output.csv"
            evidence = root / "evidence"

            source.write_text(
                CSV_TEXT,
                encoding="utf-8",
            )

            before = source.read_bytes()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "freshness_breach",
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                    "--evidence-dir",
                    str(evidence),
                ],
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

            self.assertEqual(
                source.read_bytes(),
                before,
            )

            stdout = json.loads(
                completed.stdout
            )

            self.assertEqual(
                stdout["status"],
                "PASS",
            )

            self.assertEqual(
                stdout[
                    "scenario_id"
                ],
                "freshness_breach",
            )

            self.assertEqual(
                stdout[
                    "target_dataset"
                ],
                "gold_daily_sales",
            )

            self.assertEqual(
                stdout[
                    "fault_operation"
                ],
                (
                    "shift_actual_publish_"
                    "time_beyond_slo"
                ),
            )

            self.assertEqual(
                stdout[
                    "breach_delta_seconds"
                ],
                1.0,
            )

            self.assertEqual(
                stdout[
                    "observed_age_seconds"
                ],
                86401.0,
            )

            self.assertEqual(
                stdout[
                    "maximum_age_seconds"
                ],
                86400.0,
            )

            self.assertEqual(
                stdout[
                    "freshness_status_preserved"
                ],
                "PASS",
            )

            with output.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows = list(
                    csv.DictReader(
                        handle
                    )
                )

            target = next(
                row
                for row in rows
                if row[
                    "dataset_name"
                ]
                == "gold_daily_sales"
            )

            other = next(
                row
                for row in rows
                if row[
                    "dataset_name"
                ]
                == (
                    "gold_public_"
                    "sales_dashboard"
                )
            )

            self.assertEqual(
                target[
                    "actual_publish_time"
                ],
                "2026-07-05T23:58:00",
            )

            self.assertEqual(
                target[
                    "freshness_status"
                ],
                "PASS",
            )

            self.assertEqual(
                observed_age(target),
                86401.0,
            )

            self.assertEqual(
                float(
                    target[
                        "freshness_slo_hours"
                    ]
                )
                * 3600.0,
                86400.0,
            )

            self.assertEqual(
                other[
                    "actual_publish_time"
                ],
                "2026-07-05T23:58:01",
            )

            evidence_payload = json.loads(
                (
                    evidence
                    / "fault-injection.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                evidence_payload[
                    "expected_effect"
                ][
                    "collector_source_status"
                ],
                "FAIL",
            )

            self.assertEqual(
                evidence_payload[
                    "expected_effect"
                ][
                    "primary_policy_id"
                ],
                "PAC-FRESH-001",
            )

            self.assertFalse(
                evidence_payload[
                    "safety"
                ][
                    "source_file_mutated"
                ]
            )

    def test_reinjection_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            source = root / "source.csv"
            first = root / "first.csv"
            second = root / "second.csv"

            source.write_text(
                CSV_TEXT,
                encoding="utf-8",
            )

            first_run = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "freshness_breach",
                    "--source",
                    str(source),
                    "--output",
                    str(first),
                    "--evidence-dir",
                    str(
                        root
                        / "evidence-first"
                    ),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                first_run.returncode,
                0,
                msg=first_run.stderr,
            )

            second_run = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "freshness_breach",
                    "--source",
                    str(first),
                    "--output",
                    str(second),
                    "--evidence-dir",
                    str(
                        root
                        / "evidence-second"
                    ),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(
                second_run.returncode,
                0,
            )

            self.assertIn(
                (
                    "must begin exactly at "
                    "the configured threshold"
                ),
                second_run.stderr,
            )

    def test_unsupported_post_scenario_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            source = root / "source.csv"

            source.write_text(
                CSV_TEXT,
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(INJECTOR),
                    "--scenario",
                    "policy_false_positive",
                    "--source",
                    str(source),
                    "--output",
                    str(
                        root
                        / "output.csv"
                    ),
                    "--evidence-dir",
                    str(
                        root
                        / "evidence"
                    ),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(
                completed.returncode,
                0,
            )

            self.assertIn(
                "Unsupported POST fault scenario",
                completed.stderr,
            )




class QualityRegressionInjectorTest(
    unittest.TestCase
):
    TARGET = (
        "test.thesis_pac_pipeline."
        "gold_financial_reconciliation"
    )

    @staticmethod
    def baseline_payload():
        models = [
            {
                "unique_id": (
                    "model.thesis_pac_pipeline."
                    f"synthetic_{index:02d}"
                ),
                "status": "success",
            }
            for index in range(15)
        ]

        tests = [
            {
                "unique_id": (
                    "test.thesis_pac_pipeline."
                    f"synthetic_quality_{index:02d}"
                ),
                "status": "pass",
                "failures": 0,
            }
            for index in range(40)
        ]

        tests.append(
            {
                "unique_id": (
                    QualityRegressionInjectorTest
                    .TARGET
                ),
                "status": "pass",
                "failures": 0,
                "message": None,
            }
        )

        return {
            "metadata": {
                "dbt_schema_version": (
                    "https://schemas.getdbt.com/"
                    "dbt/run-results/v6.json"
                ),
            },
            "results": models + tests,
            "elapsed_time": 1.0,
        }

    @staticmethod
    def injector_path():
        return (
            Path(__file__).resolve()
            .parents[2]
            / "scripts"
            / "experiments"
            / "inject_post_fault_scenario.py"
        )

    def test_quality_regression_uses_copy_and_marks_one_test_failed(
        self,
    ):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        import sys

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            source_file = (
                root
                / "run_results.json"
            )

            output_file = (
                root
                / "fault"
                / "run_results.json"
            )

            evidence_dir = (
                root
                / "evidence"
            )

            payload = (
                self.baseline_payload()
            )

            source_file.write_text(
                json.dumps(
                    payload,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            source_before = (
                source_file.read_bytes()
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        self.injector_path()
                    ),
                    "--scenario",
                    "quality_regression",
                    "--source",
                    str(source_file),
                    "--output",
                    str(output_file),
                    "--evidence-dir",
                    str(evidence_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                completed.returncode,
                0,
                msg=completed.stderr,
            )

            self.assertEqual(
                source_file.read_bytes(),
                source_before,
            )

            output = json.loads(
                output_file.read_text(
                    encoding="utf-8"
                )
            )

            before_by_id = {
                result["unique_id"]: result
                for result
                in payload["results"]
            }

            after_by_id = {
                result["unique_id"]: result
                for result
                in output["results"]
            }

            self.assertEqual(
                set(before_by_id),
                set(after_by_id),
            )

            target = after_by_id[
                self.TARGET
            ]

            self.assertEqual(
                target["status"],
                "fail",
            )

            self.assertEqual(
                target["failures"],
                1,
            )

            changed = [
                unique_id
                for unique_id
                in before_by_id
                if (
                    before_by_id[
                        unique_id
                    ]
                    != after_by_id[
                        unique_id
                    ]
                )
            ]

            self.assertEqual(
                changed,
                [
                    self.TARGET,
                ],
            )

            failed_tests = [
                result
                for result
                in output["results"]
                if (
                    str(
                        result.get(
                            "unique_id",
                            "",
                        )
                    ).startswith(
                        "test."
                    )
                    and result.get(
                        "status"
                    )
                    != "pass"
                )
            ]

            self.assertEqual(
                len(failed_tests),
                1,
            )

            evidence = json.loads(
                (
                    evidence_dir
                    / "fault-injection.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                evidence[
                    "scenario_id"
                ],
                "quality_regression",
            )

            self.assertEqual(
                evidence[
                    "target_test"
                ],
                self.TARGET,
            )

            self.assertEqual(
                evidence[
                    "expected_effect"
                ][
                    "collector_quality_status"
                ],
                "FAIL",
            )

            self.assertEqual(
                evidence[
                    "expected_effect"
                ][
                    "collector_failed_tests"
                ],
                1,
            )

            self.assertEqual(
                evidence[
                    "expected_effect"
                ][
                    "collector_critical_failures"
                ],
                [
                    self.TARGET,
                ],
            )

            self.assertFalse(
                evidence[
                    "safety"
                ][
                    "source_file_mutated"
                ]
            )

    def test_quality_regression_rejects_non_clean_baseline(
        self,
    ):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        import sys

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            source_file = (
                root
                / "run_results.json"
            )

            output_file = (
                root
                / "fault.json"
            )

            evidence_dir = (
                root
                / "evidence"
            )

            payload = (
                self.baseline_payload()
            )

            payload[
                "results"
            ][15][
                "status"
            ] = "fail"

            payload[
                "results"
            ][15][
                "failures"
            ] = 1

            source_file.write_text(
                json.dumps(
                    payload,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        self.injector_path()
                    ),
                    "--scenario",
                    "quality_regression",
                    "--source",
                    str(source_file),
                    "--output",
                    str(output_file),
                    "--evidence-dir",
                    str(evidence_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(
                completed.returncode,
                0,
            )

            self.assertIn(
                (
                    "must begin with all "
                    "governed dbt tests passing"
                ),
                completed.stderr,
            )

            self.assertFalse(
                output_file.exists()
            )



if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
