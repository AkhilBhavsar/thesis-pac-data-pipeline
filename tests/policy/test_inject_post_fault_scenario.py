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
                    "quality_regression",
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


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
