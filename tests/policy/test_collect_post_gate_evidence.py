from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

MODULE_PATH = (
    REPO_ROOT
    / "scripts"
    / "policy"
    / "collect_post_gate_evidence.py"
)

SPEC = importlib.util.spec_from_file_location(
    "collect_post_gate_evidence",
    MODULE_PATH,
)

assert SPEC is not None
assert SPEC.loader is not None

collector = importlib.util.module_from_spec(
    SPEC
)

SPEC.loader.exec_module(
    collector
)

SAFE_FIXTURE = (
    REPO_ROOT
    / "policies"
    / "fixtures"
    / "c1-safe-baseline.json"
)


def write_json(
    path: Path,
    payload: object,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_freshness(
    path: Path,
    rows: list[dict[str, str]],
) -> None:
    fieldnames = [
        "dataset_name",
        "expected_publish_time",
        "actual_publish_time",
        "freshness_slo_hours",
        "freshness_status",
        "run_id",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


def base_files(
    tmp_path: Path,
) -> dict[str, Path]:
    fixture = json.loads(
        SAFE_FIXTURE.read_text(
            encoding="utf-8"
        )
    )

    pre = {
        key: fixture[key]
        for key in [
            "metadata",
            "schema_contract",
            "transformation",
            "privacy",
        ]
    }

    files = {
        "pre": tmp_path / "pre.json",
        "run_results": (
            tmp_path
            / "run_results.json"
        ),
        "dagster": (
            tmp_path
            / "dagster-summary.json"
        ),
        "canonical": (
            tmp_path
            / "canonical-comparison.json"
        ),
        "isolated": (
            tmp_path
            / "isolated-inventory.json"
        ),
        "athena": (
            tmp_path
            / "athena-query-inventory.json"
        ),
        "freshness": (
            tmp_path
            / "freshness_control.csv"
        ),
    }

    write_json(
        files["pre"],
        pre,
    )

    write_json(
        files["run_results"],
        {
            "results": [
                {
                    "unique_id": (
                        "model.thesis.example"
                    ),
                    "status": "success",
                },
                {
                    "unique_id": (
                        "test.thesis.first"
                    ),
                    "status": "pass",
                },
                {
                    "unique_id": (
                        "test.thesis.second"
                    ),
                    "status": "pass",
                },
            ]
        },
    )

    write_json(
        files["dagster"],
        {
            "status": "PASS",
            "success": True,
        },
    )

    write_json(
        files["canonical"],
        {
            "status": "PASS",
            "changed": False,
        },
    )

    write_json(
        files["isolated"],
        {
            "status": "PASS",
            "total_tables": 15,
        },
    )

    write_json(
        files["athena"],
        {
            "status": "PASS",
            "failed_query_count": 0,
        },
    )

    write_freshness(
        files["freshness"],
        [
            {
                "dataset_name": (
                    "gold_daily_sales"
                ),
                "expected_publish_time": (
                    "2026-07-06T23:58:01"
                ),
                "actual_publish_time": (
                    "2026-07-05T23:58:01"
                ),
                "freshness_slo_hours": "24",
                "freshness_status": "PASS",
                "run_id": "baseline_run_001",
            }
        ],
    )

    return files


def collect(
    files: dict[str, Path],
) -> dict:
    return collector.collect_post_evidence(
        pre_evidence_path=(
            files["pre"]
        ),
        run_results_path=(
            files["run_results"]
        ),
        dagster_summary_path=(
            files["dagster"]
        ),
        canonical_comparison_path=(
            files["canonical"]
        ),
        isolated_inventory_path=(
            files["isolated"]
        ),
        athena_query_inventory_path=(
            files["athena"]
        ),
        freshness_control_path=(
            files["freshness"]
        ),
    )


def test_safe_post_execution_mapping(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    result = collect(
        files
    )

    assert result["quality"] == {
        "status": "PASS",
        "total_tests": 2,
        "failed_tests": 0,
        "critical_failures": [],
    }

    assert result[
        "freshness"
    ][
        "status"
    ] == "PASS"

    source = result[
        "freshness"
    ][
        "sources"
    ][0]

    assert source[
        "source"
    ] == "gold_daily_sales"

    assert source[
        "observed_age_seconds"
    ] == 86400.0

    assert source[
        "maximum_age_seconds"
    ] == 86400.0

    assert source[
        "status"
    ] == "PASS"

    assert result["runtime"] == {
        "pipeline_status": "PASS",
        "canonical_unchanged": True,
        "isolated_output_tables": 15,
        "athena_failed_queries": 0,
    }


def test_quality_failure_is_preserved(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    write_json(
        files["run_results"],
        {
            "results": [
                {
                    "unique_id": (
                        "test.thesis.critical"
                    ),
                    "status": "fail",
                }
            ]
        },
    )

    result = collect(
        files
    )

    assert result["quality"] == {
        "status": "FAIL",
        "total_tests": 1,
        "failed_tests": 1,
        "critical_failures": [
            "test.thesis.critical"
        ],
    }


def test_freshness_status_failure_is_preserved(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    write_freshness(
        files["freshness"],
        [
            {
                "dataset_name": (
                    "gold_daily_sales"
                ),
                "expected_publish_time": (
                    "2026-07-06T00:00:00"
                ),
                "actual_publish_time": (
                    "2026-07-05T23:55:00"
                ),
                "freshness_slo_hours": "24",
                "freshness_status": "FAIL",
                "run_id": "failure_run",
            }
        ],
    )

    result = collect(
        files
    )

    assert result[
        "freshness"
    ][
        "status"
    ] == "FAIL"

    assert result[
        "freshness"
    ][
        "sources"
    ][0][
        "status"
    ] == "FAIL"


def test_freshness_threshold_overrun_fails(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    write_freshness(
        files["freshness"],
        [
            {
                "dataset_name": (
                    "gold_daily_sales"
                ),
                "expected_publish_time": (
                    "2026-07-06T00:00:01"
                ),
                "actual_publish_time": (
                    "2026-07-05T00:00:00"
                ),
                "freshness_slo_hours": "24",
                "freshness_status": "PASS",
                "run_id": "threshold_run",
            }
        ],
    )

    result = collect(
        files
    )

    source = result[
        "freshness"
    ][
        "sources"
    ][0]

    assert source[
        "observed_age_seconds"
    ] == 86401.0

    assert source[
        "maximum_age_seconds"
    ] == 86400.0

    assert source[
        "status"
    ] == "FAIL"

    assert result[
        "freshness"
    ][
        "status"
    ] == "FAIL"


def test_negative_freshness_age_is_clamped(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    write_freshness(
        files["freshness"],
        [
            {
                "dataset_name": (
                    "gold_daily_sales"
                ),
                "expected_publish_time": (
                    "2026-07-05T00:00:00"
                ),
                "actual_publish_time": (
                    "2026-07-06T00:00:00"
                ),
                "freshness_slo_hours": "24",
                "freshness_status": "PASS",
                "run_id": "future_publish",
            }
        ],
    )

    result = collect(
        files
    )

    assert result[
        "freshness"
    ][
        "sources"
    ][0][
        "observed_age_seconds"
    ] == 0.0


def test_runtime_failure_fields_are_preserved(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    write_json(
        files["dagster"],
        {
            "status": "FAIL",
            "success": False,
        },
    )

    write_json(
        files["canonical"],
        {
            "status": "FAIL",
            "changed": True,
        },
    )

    write_json(
        files["isolated"],
        {
            "status": "FAIL",
            "total_tables": 14,
        },
    )

    write_json(
        files["athena"],
        {
            "status": "FAIL",
            "failed_query_count": 1,
        },
    )

    result = collect(
        files
    )

    assert result["runtime"] == {
        "pipeline_status": "FAIL",
        "canonical_unchanged": False,
        "isolated_output_tables": 14,
        "athena_failed_queries": 1,
    }


def test_invalid_freshness_status_fails_closed(
    tmp_path: Path,
) -> None:
    files = base_files(
        tmp_path
    )

    write_freshness(
        files["freshness"],
        [
            {
                "dataset_name": (
                    "gold_daily_sales"
                ),
                "expected_publish_time": (
                    "2026-07-06T00:00:00"
                ),
                "actual_publish_time": (
                    "2026-07-05T00:00:00"
                ),
                "freshness_slo_hours": "24",
                "freshness_status": "UNKNOWN",
                "run_id": "invalid",
            }
        ],
    )

    with pytest.raises(
        collector.EvidenceError
    ):
        collect(
            files
        )
