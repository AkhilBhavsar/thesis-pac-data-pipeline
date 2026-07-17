from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "experiments" / "results"
LOGS_DIR = ROOT / "logs"

RUN_SUMMARY_PATH = (
    RESULTS_DIR
    / "local_c0_run_summary.json"
)

STAGE_RESULTS_PATH = (
    RESULTS_DIR
    / "local_c0_stage_results.csv"
)

EXPECTED_STAGES = [
    "silver_build",
    "silver_validation",
    "gold_build",
    "gold_validation",
    "gold_contract_validation",
]


def record_check(
    results: list[dict[str, Any]],
    check_name: str,
    passed: bool,
    observed_value: Any,
    expected_value: Any,
    details: str = "",
) -> None:
    """Append one C0 baseline validation result."""
    results.append(
        {
            "condition": "C0",
            "check_name": check_name,
            "status": (
                "PASS"
                if passed
                else "FAIL"
            ),
            "severity": "critical",
            "observed_value": observed_value,
            "expected_value": expected_value,
            "details": details,
        }
    )


def main() -> None:
    """Validate local C0 execution evidence."""
    started_at = datetime.now(
        timezone.utc
    )

    print(
        "Starting local C0 baseline validation...\n"
    )

    results: list[
        dict[str, Any]
    ] = []

    record_check(
        results,
        "run_summary_exists",
        RUN_SUMMARY_PATH.exists(),
        str(
            RUN_SUMMARY_PATH.relative_to(ROOT)
        ),
        "file exists",
    )

    record_check(
        results,
        "stage_results_exist",
        STAGE_RESULTS_PATH.exists(),
        str(
            STAGE_RESULTS_PATH.relative_to(ROOT)
        ),
        "file exists",
    )

    if (
        not RUN_SUMMARY_PATH.exists()
        or not STAGE_RESULTS_PATH.exists()
    ):
        summary = {}
        stages = pd.DataFrame()
    else:
        summary = json.loads(
            RUN_SUMMARY_PATH.read_text(
                encoding="utf-8"
            )
        )

        stages = pd.read_csv(
            STAGE_RESULTS_PATH,
            low_memory=False,
        )

    if summary:
        record_check(
            results,
            "condition_is_c0",
            summary.get("condition") == "C0",
            summary.get("condition"),
            "C0",
        )

        record_check(
            results,
            "environment_is_local",
            (
                summary.get("environment")
                == "local"
            ),
            summary.get("environment"),
            "local",
        )

        record_check(
            results,
            "overall_status_pass",
            (
                summary.get("overall_status")
                == "PASS"
            ),
            summary.get("overall_status"),
            "PASS",
        )

        record_check(
            results,
            "policy_as_code_disabled",
            (
                summary.get(
                    "policy_as_code_enabled"
                )
                is False
            ),
            summary.get(
                "policy_as_code_enabled"
            ),
            False,
        )

        record_check(
            results,
            "bounded_self_healing_disabled",
            (
                summary.get(
                    "bounded_self_healing_enabled"
                )
                is False
            ),
            summary.get(
                "bounded_self_healing_enabled"
            ),
            False,
        )

        record_check(
            results,
            "automatic_remediation_disabled",
            (
                summary.get(
                    "automatic_remediation_enabled"
                )
                is False
            ),
            summary.get(
                "automatic_remediation_enabled"
            ),
            False,
        )

        record_check(
            results,
            "all_stages_executed",
            (
                summary.get(
                    "executed_stage_count"
                )
                == len(EXPECTED_STAGES)
            ),
            summary.get(
                "executed_stage_count"
            ),
            len(EXPECTED_STAGES),
        )

        record_check(
            results,
            "no_failed_stages",
            (
                summary.get(
                    "failed_stages"
                )
                == 0
            ),
            summary.get(
                "failed_stages"
            ),
            0,
        )

        duration = summary.get(
            "total_duration_seconds"
        )

        record_check(
            results,
            "positive_pipeline_duration",
            (
                isinstance(
                    duration,
                    (int, float),
                )
                and duration > 0
            ),
            duration,
            "> 0",
        )

        evidence = summary.get(
            "evidence",
            {},
        )

        expected_evidence = {
            "silver_dataset_count": 10,
            "silver_validation_status": "PASS",
            "silver_validation_checks": 53,
            "silver_validation_failures": 0,
            "gold_dataset_count": 5,
            "delivered_order_count": 96478,
            "delivered_item_count": 110197,
            "gold_validation_status": "PASS",
            "gold_validation_checks": 110,
            "gold_validation_failures": 0,
            "gold_contract_status": "PASS",
            "gold_contract_count": 5,
            "gold_contract_checks": 211,
            "gold_contract_failures": 0,
            "gold_determinism_validated_separately": True,
            "gold_deterministic_datasets": 5,
        }

        for key, expected in (
            expected_evidence.items()
        ):
            observed = evidence.get(key)

            record_check(
                results,
                f"evidence_{key}",
                observed == expected,
                observed,
                expected,
            )

    if not stages.empty:
        actual_stages = (
            stages
            .sort_values("stage_order")
            ["stage_name"]
            .tolist()
        )

        record_check(
            results,
            "stage_sequence_correct",
            actual_stages == EXPECTED_STAGES,
            json.dumps(actual_stages),
            json.dumps(EXPECTED_STAGES),
        )

        failed_stage_rows = int(
            (
                stages["status"]
                != "PASS"
            ).sum()
        )

        record_check(
            results,
            "all_stage_rows_pass",
            failed_stage_rows == 0,
            failed_stage_rows,
            0,
        )

        nonzero_exit_codes = int(
            (
                stages["exit_code"]
                != 0
            ).sum()
        )

        record_check(
            results,
            "all_stage_exit_codes_zero",
            nonzero_exit_codes == 0,
            nonzero_exit_codes,
            0,
        )

        invalid_durations = int(
            (
                stages["duration_seconds"]
                <= 0
            ).sum()
        )

        record_check(
            results,
            "all_stage_durations_positive",
            invalid_durations == 0,
            invalid_durations,
            0,
        )

    completed_at = datetime.now(
        timezone.utc
    )

    result_frame = pd.DataFrame(
        results
    )

    results_path = (
        RESULTS_DIR
        / "local_c0_validation_results.csv"
    )

    result_frame.to_csv(
        results_path,
        index=False,
    )

    passed_checks = int(
        (
            result_frame["status"]
            == "PASS"
        ).sum()
    )

    failed_checks = int(
        (
            result_frame["status"]
            == "FAIL"
        ).sum()
    )

    overall_status = (
        "PASS"
        if failed_checks == 0
        else "FAIL"
    )

    validation_summary = {
        "validation_started_at": (
            started_at.isoformat()
        ),
        "validation_completed_at": (
            completed_at.isoformat()
        ),
        "duration_seconds": round(
            (
                completed_at
                - started_at
            ).total_seconds(),
            4,
        ),
        "condition": "C0",
        "overall_status": overall_status,
        "total_checks": len(
            result_frame
        ),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "critical_failures": failed_checks,
    }

    summary_path = (
        RESULTS_DIR
        / "local_c0_validation_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            validation_summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "Local C0 baseline validation completed."
    )
    print(f"Overall status: {overall_status}")
    print(f"Passed checks: {passed_checks}")
    print(f"Failed checks: {failed_checks}")
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")

    if failed_checks > 0:
        print("\nFailures:")

        print(
            result_frame[
                result_frame["status"]
                == "FAIL"
            ].to_string(index=False)
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()