#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCENARIO = "freshness_breach"

QUALITY_SCENARIO = "quality_regression"
QUALITY_TARGET_TEST = (
    "test.thesis_pac_pipeline."
    "gold_financial_reconciliation"
)
QUALITY_FAULT_OPERATION = (
    "mark_governed_gold_test_failed_"
    "in_evidence_copy"
)
QUALITY_EXPECTED_MODELS = 15
QUALITY_EXPECTED_TESTS = 41

TARGET_DATASET = "gold_daily_sales"

FAULT_OPERATION = (
    "shift_actual_publish_time_beyond_slo"
)

BREACH_DELTA_SECONDS = 1.0

REQUIRED_COLUMNS = {
    "dataset_name",
    "expected_publish_time",
    "actual_publish_time",
    "freshness_slo_hours",
    "freshness_status",
    "run_id",
}


def sha256_bytes(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def sha256_file(
    target_file: Path,
) -> str:
    return sha256_bytes(
        target_file.read_bytes()
    )


def atomic_write_text(
    target_file: Path,
    text: str,
) -> None:
    target_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = target_file.with_name(
        f".{target_file.name}.tmp"
    )

    temporary.write_text(
        text,
        encoding="utf-8",
    )

    temporary.replace(
        target_file
    )


def write_json(
    target_file: Path,
    payload: dict[str, Any],
) -> None:
    atomic_write_text(
        target_file,
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def parse_timestamp(
    value: str,
    *,
    label: str,
) -> datetime:
    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        return datetime.fromisoformat(
            normalized
        )
    except ValueError as error:
        raise RuntimeError(
            f"Invalid timestamp for "
            f"{label}: {value!r}"
        ) from error


def render_timestamp(
    value: datetime,
    *,
    original: str,
) -> str:
    if original.strip().endswith("Z"):
        if value.tzinfo is None:
            raise RuntimeError(
                "Cannot preserve Z timestamp "
                "from a naive datetime."
            )

        return (
            value.astimezone(
                timezone.utc
            )
            .replace(
                tzinfo=None
            )
            .isoformat(
                timespec="seconds"
            )
            + "Z"
        )

    return value.isoformat(
        timespec="seconds"
    )


def parse_freshness_csv(
    content: str,
) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(
        io.StringIO(content)
    )

    fieldnames = list(
        reader.fieldnames
        or []
    )

    missing = (
        REQUIRED_COLUMNS
        - set(fieldnames)
    )

    if missing:
        raise RuntimeError(
            "Freshness control missing "
            f"required columns: "
            f"{sorted(missing)}"
        )

    rows = list(reader)

    if not rows:
        raise RuntimeError(
            "Freshness control contains "
            "no rows."
        )

    return fieldnames, rows


def render_freshness_csv(
    *,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> str:
    buffer = io.StringIO(
        newline=""
    )

    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\n",
    )

    writer.writeheader()
    writer.writerows(rows)

    return buffer.getvalue()


def inject_freshness_breach(
    *,
    source: Path,
    output: Path,
    evidence_dir: Path,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()

    if source == output:
        raise RuntimeError(
            "Freshness fault output must "
            "not overwrite the source file."
        )

    if not source.is_file():
        raise RuntimeError(
            "Freshness source does not exist: "
            f"{source}"
        )

    source_bytes_before = (
        source.read_bytes()
    )

    source_sha_before = (
        sha256_bytes(
            source_bytes_before
        )
    )

    source_text = (
        source_bytes_before.decode(
            "utf-8"
        )
    )

    fieldnames, rows = (
        parse_freshness_csv(
            source_text
        )
    )

    matching = [
        row
        for row in rows
        if row[
            "dataset_name"
        ].strip()
        == TARGET_DATASET
    ]

    if len(matching) != 1:
        raise RuntimeError(
            "Expected exactly one "
            f"{TARGET_DATASET} freshness row; "
            f"found {len(matching)}."
        )

    target = matching[0]

    source_status = target[
        "freshness_status"
    ].strip().upper()

    if source_status != "PASS":
        raise RuntimeError(
            "Freshness breach baseline "
            "must begin with "
            "freshness_status=PASS."
        )

    expected = parse_timestamp(
        target[
            "expected_publish_time"
        ],
        label=(
            f"{TARGET_DATASET}."
            "expected_publish_time"
        ),
    )

    actual_before = parse_timestamp(
        target[
            "actual_publish_time"
        ],
        label=(
            f"{TARGET_DATASET}."
            "actual_publish_time"
        ),
    )

    if (
        expected.tzinfo
        != actual_before.tzinfo
    ):
        raise RuntimeError(
            "Expected and actual freshness "
            "timestamps use incompatible "
            "timezone forms."
        )

    try:
        slo_hours = float(
            target[
                "freshness_slo_hours"
            ]
        )
    except ValueError as error:
        raise RuntimeError(
            "freshness_slo_hours "
            "must be numeric."
        ) from error

    if slo_hours < 0:
        raise RuntimeError(
            "freshness_slo_hours "
            "must be non-negative."
        )

    maximum_age_seconds = (
        slo_hours
        * 3600.0
    )

    observed_before = max(
        0.0,
        (
            expected
            - actual_before
        ).total_seconds(),
    )

    if abs(
        observed_before
        - maximum_age_seconds
    ) > 1e-9:
        raise RuntimeError(
            "Freshness breach baseline "
            "must begin exactly at the "
            "configured threshold; "
            f"observed={observed_before}, "
            f"maximum={maximum_age_seconds}."
        )

    injected_age_seconds = (
        maximum_age_seconds
        + BREACH_DELTA_SECONDS
    )

    actual_after = (
        expected
        - timedelta(
            seconds=(
                injected_age_seconds
            )
        )
    )

    target[
        "actual_publish_time"
    ] = render_timestamp(
        actual_after,
        original=target[
            "actual_publish_time"
        ],
    )

    if (
        target[
            "freshness_status"
        ].strip().upper()
        != "PASS"
    ):
        raise RuntimeError(
            "Injector unexpectedly changed "
            "freshness_status."
        )

    observed_after = max(
        0.0,
        (
            expected
            - actual_after
        ).total_seconds(),
    )

    if not (
        observed_after
        > maximum_age_seconds
    ):
        raise RuntimeError(
            "Injected freshness age did "
            "not breach the SLO."
        )

    if abs(
        observed_after
        - injected_age_seconds
    ) > 1e-9:
        raise RuntimeError(
            "Injected freshness age "
            "is not deterministic."
        )

    output_text = (
        render_freshness_csv(
            fieldnames=fieldnames,
            rows=rows,
        )
    )

    if output_text == source_text:
        raise RuntimeError(
            "Freshness injection produced "
            "no change."
        )

    atomic_write_text(
        output,
        output_text,
    )

    source_sha_after = (
        sha256_file(
            source
        )
    )

    if (
        source_sha_after
        != source_sha_before
    ):
        raise RuntimeError(
            "Source freshness control "
            "was mutated."
        )

    output_sha = (
        sha256_file(
            output
        )
    )

    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    patch = "".join(
        difflib.unified_diff(
            source_text.splitlines(
                keepends=True
            ),
            output_text.splitlines(
                keepends=True
            ),
            fromfile=(
                "a/freshness_control.csv"
            ),
            tofile=(
                "b/freshness_control.csv"
            ),
        )
    )

    atomic_write_text(
        evidence_dir
        / "fault-injection.patch",
        patch,
    )

    payload = {
        "schema_version": "1.0.0",
        "recorded_at_utc": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        ),
        "condition": "C1",
        "scenario_id": SCENARIO,
        "fault_class": (
            "controlled_freshness_"
            "threshold_breach"
        ),
        "injection_scope": (
            "ephemeral_post_execution_"
            "evidence_copy"
        ),
        "target_dataset": (
            TARGET_DATASET
        ),
        "fault": {
            "operation": (
                FAULT_OPERATION
            ),
            "breach_delta_seconds": (
                BREACH_DELTA_SECONDS
            ),
            "freshness_status_preserved": (
                "PASS"
            ),
        },
        "baseline": {
            "expected_publish_time": (
                target[
                    "expected_publish_time"
                ]
            ),
            "actual_publish_time": (
                actual_before.isoformat(
                    timespec="seconds"
                )
            ),
            "freshness_slo_hours": (
                slo_hours
            ),
            "observed_age_seconds": (
                observed_before
            ),
            "maximum_age_seconds": (
                maximum_age_seconds
            ),
            "freshness_status": (
                source_status
            ),
        },
        "injected": {
            "expected_publish_time": (
                target[
                    "expected_publish_time"
                ]
            ),
            "actual_publish_time": (
                target[
                    "actual_publish_time"
                ]
            ),
            "freshness_slo_hours": (
                slo_hours
            ),
            "observed_age_seconds": (
                observed_after
            ),
            "maximum_age_seconds": (
                maximum_age_seconds
            ),
            "freshness_status": (
                target[
                    "freshness_status"
                ]
            ),
        },
        "expected_effect": {
            "collector_source_status": (
                "FAIL"
            ),
            "collector_aggregate_status": (
                "FAIL"
            ),
            "primary_policy_id": (
                "PAC-FRESH-001"
            ),
            "release_policy_id": (
                "PAC-RELEASE-001"
            ),
            "expected_stage": "post",
            "expected_decision": (
                "DENY"
            ),
            "promotion": "BLOCKED",
        },
        "safety": {
            "source_file_mutated": False,
            "canonical_data_mutated": False,
            "aws_mutation_performed": False,
            "self_healing_permitted": False,
            "automatic_remediation_permitted": (
                False
            ),
        },
        "source_sha256": (
            source_sha_before
        ),
        "output_sha256": (
            output_sha
        ),
    }

    write_json(
        evidence_dir
        / "fault-injection.json",
        payload,
    )

    return payload



def inject_quality_regression(
    *,
    source: Path,
    output: Path,
    evidence_dir: Path,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()

    if source == output:
        raise RuntimeError(
            "Quality fault output must not "
            "overwrite the source run_results."
        )

    if not source.is_file():
        raise RuntimeError(
            "Quality run_results source "
            f"does not exist: {source}"
        )

    source_bytes_before = (
        source.read_bytes()
    )

    source_sha_before = sha256_bytes(
        source_bytes_before
    )

    try:
        payload = json.loads(
            source_bytes_before.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(
            "Quality run_results source "
            "is not valid UTF-8 JSON."
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "Quality run_results root "
            "must be an object."
        )

    results = payload.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):
        raise RuntimeError(
            "Quality run_results.results "
            "must be an array."
        )

    if not all(
        isinstance(
            result,
            dict,
        )
        for result in results
    ):
        raise RuntimeError(
            "Quality run_results contains "
            "a non-object result."
        )

    model_results = [
        result
        for result in results
        if str(
            result.get(
                "unique_id",
                "",
            )
        ).startswith(
            "model."
        )
    ]

    test_results = [
        result
        for result in results
        if str(
            result.get(
                "unique_id",
                "",
            )
        ).startswith(
            "test."
        )
    ]

    if (
        len(model_results)
        != QUALITY_EXPECTED_MODELS
    ):
        raise RuntimeError(
            "Quality regression baseline "
            "must contain exactly "
            f"{QUALITY_EXPECTED_MODELS} "
            "model results; found "
            f"{len(model_results)}."
        )

    if (
        len(test_results)
        != QUALITY_EXPECTED_TESTS
    ):
        raise RuntimeError(
            "Quality regression baseline "
            "must contain exactly "
            f"{QUALITY_EXPECTED_TESTS} "
            "test results; found "
            f"{len(test_results)}."
        )

    model_failures = [
        result
        for result in model_results
        if result.get(
            "status"
        )
        != "success"
    ]

    if model_failures:
        raise RuntimeError(
            "Quality regression baseline "
            "must begin with all models "
            "successful."
        )

    baseline_test_failures = [
        result
        for result in test_results
        if result.get(
            "status"
        )
        != "pass"
    ]

    if baseline_test_failures:
        raise RuntimeError(
            "Quality regression baseline "
            "must begin with all governed "
            "dbt tests passing."
        )

    matching = [
        result
        for result in test_results
        if result.get(
            "unique_id"
        )
        == QUALITY_TARGET_TEST
    ]

    if len(matching) != 1:
        raise RuntimeError(
            "Expected exactly one "
            f"{QUALITY_TARGET_TEST} result; "
            f"found {len(matching)}."
        )

    target_before = matching[0]

    if (
        target_before.get(
            "failures"
        )
        != 0
    ):
        raise RuntimeError(
            "Quality regression target "
            "must begin with failures=0."
        )

    output_payload = json.loads(
        json.dumps(payload)
    )

    output_results = output_payload[
        "results"
    ]

    output_matching = [
        result
        for result in output_results
        if result.get(
            "unique_id"
        )
        == QUALITY_TARGET_TEST
    ]

    if len(output_matching) != 1:
        raise RuntimeError(
            "Quality output target "
            "resolution failed."
        )

    target_after = output_matching[0]

    target_after[
        "status"
    ] = "fail"

    target_after[
        "failures"
    ] = 1

    expected_target = dict(
        target_before
    )

    expected_target[
        "status"
    ] = "fail"

    expected_target[
        "failures"
    ] = 1

    if target_after != expected_target:
        raise RuntimeError(
            "Quality injector changed "
            "unexpected target fields."
        )

    before_by_id = {
        result.get(
            "unique_id"
        ): result
        for result in results
    }

    after_by_id = {
        result.get(
            "unique_id"
        ): result
        for result in output_results
    }

    if (
        set(before_by_id)
        != set(after_by_id)
    ):
        raise RuntimeError(
            "Quality injector changed "
            "the dbt result inventory."
        )

    unexpected_changes = [
        unique_id
        for unique_id
        in before_by_id
        if (
            unique_id
            != QUALITY_TARGET_TEST
            and before_by_id[
                unique_id
            ]
            != after_by_id[
                unique_id
            ]
        )
    ]

    if unexpected_changes:
        raise RuntimeError(
            "Quality injector changed "
            "non-target dbt results: "
            f"{sorted(unexpected_changes)}"
        )

    output_test_results = [
        result
        for result in output_results
        if str(
            result.get(
                "unique_id",
                "",
            )
        ).startswith(
            "test."
        )
    ]

    output_failures = [
        result
        for result in output_test_results
        if result.get(
            "status"
        )
        != "pass"
    ]

    if len(
        output_failures
    ) != 1:
        raise RuntimeError(
            "Injected quality evidence "
            "must contain exactly one "
            "failed test."
        )

    if (
        output_failures[0].get(
            "unique_id"
        )
        != QUALITY_TARGET_TEST
    ):
        raise RuntimeError(
            "Injected failed test "
            "is not the controlled target."
        )

    output_text = (
        json.dumps(
            output_payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    atomic_write_text(
        output,
        output_text,
    )

    source_sha_after = sha256_file(
        source
    )

    if (
        source_sha_after
        != source_sha_before
    ):
        raise RuntimeError(
            "Source dbt run_results "
            "was mutated."
        )

    output_sha = sha256_file(
        output
    )

    if (
        output_sha
        == source_sha_before
    ):
        raise RuntimeError(
            "Quality injection produced "
            "no evidence change."
        )

    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    patch = "\n".join(
        [
            "--- a/run_results.json",
            "+++ b/run_results.json",
            (
                "@@ controlled POST quality "
                "validation outcome @@"
            ),
            (
                f" target_test="
                f"{QUALITY_TARGET_TEST}"
            ),
            '- "status": "pass"',
            '+ "status": "fail"',
            '- "failures": 0',
            '+ "failures": 1',
            "",
        ]
    )

    atomic_write_text(
        evidence_dir
        / "fault-injection.patch",
        patch,
    )

    payload_out = {
        "schema_version": "1.0.0",
        "recorded_at_utc": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        ),
        "condition": "C1",
        "scenario_id": (
            QUALITY_SCENARIO
        ),
        "fault_class": (
            "controlled_governed_gold_"
            "quality_validation_failure"
        ),
        "injection_scope": (
            "ephemeral_post_execution_"
            "evidence_copy"
        ),
        "target_test": (
            QUALITY_TARGET_TEST
        ),
        "fault": {
            "operation": (
                QUALITY_FAULT_OPERATION
            ),
            "status_before": "pass",
            "status_after": "fail",
            "failures_before": 0,
            "failures_after": 1,
        },
        "baseline": {
            "model_results": (
                len(model_results)
            ),
            "test_results": (
                len(test_results)
            ),
            "failed_tests": 0,
            "target_status": (
                target_before[
                    "status"
                ]
            ),
            "target_failures": (
                target_before[
                    "failures"
                ]
            ),
        },
        "injected": {
            "model_results": (
                len(model_results)
            ),
            "test_results": (
                len(
                    output_test_results
                )
            ),
            "failed_tests": (
                len(
                    output_failures
                )
            ),
            "target_status": (
                target_after[
                    "status"
                ]
            ),
            "target_failures": (
                target_after[
                    "failures"
                ]
            ),
        },
        "expected_effect": {
            "collector_quality_status": (
                "FAIL"
            ),
            "collector_total_tests": (
                QUALITY_EXPECTED_TESTS
            ),
            "collector_failed_tests": 1,
            "collector_critical_failures": [
                QUALITY_TARGET_TEST,
            ],
            "primary_policy_id": (
                "PAC-QUALITY-001"
            ),
            "release_policy_id": (
                "PAC-RELEASE-001"
            ),
            "expected_stage": "post",
            "expected_decision": "DENY",
            "promotion": "BLOCKED",
        },
        "safety": {
            "source_file_mutated": False,
            "canonical_data_mutated": False,
            "aws_mutation_performed": False,
            "self_healing_permitted": False,
            "automatic_remediation_permitted": (
                False
            ),
        },
        "source_sha256": (
            source_sha_before
        ),
        "output_sha256": (
            output_sha
        ),
    }

    write_json(
        evidence_dir
        / "fault-injection.json",
        payload_out,
    )

    return payload_out


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()

    result.add_argument(
        "--scenario",
        required=True,
    )

    result.add_argument(
        "--source",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--evidence-dir",
        required=True,
        type=Path,
    )

    return result


def main() -> int:
    args = parser().parse_args()

    try:
        if args.scenario == SCENARIO:
            payload = (
                inject_freshness_breach(
                    source=args.source,
                    output=args.output,
                    evidence_dir=(
                        args.evidence_dir
                    ),
                )
            )
        elif (
            args.scenario
            == QUALITY_SCENARIO
        ):
            payload = (
                inject_quality_regression(
                    source=args.source,
                    output=args.output,
                    evidence_dir=(
                        args.evidence_dir
                    ),
                )
            )
        else:
            raise RuntimeError(
                "Unsupported POST "
                "fault scenario: "
                f"{args.scenario}"
            )
    except RuntimeError as error:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )

        return 1

    if args.scenario == SCENARIO:
        summary = {
            "status": "PASS",
            "scenario_id": (
                payload[
                    "scenario_id"
                ]
            ),
            "target_dataset": (
                payload[
                    "target_dataset"
                ]
            ),
            "fault_operation": (
                payload[
                    "fault"
                ][
                    "operation"
                ]
            ),
            "breach_delta_seconds": (
                payload[
                    "fault"
                ][
                    "breach_delta_seconds"
                ]
            ),
            "observed_age_seconds": (
                payload[
                    "injected"
                ][
                    "observed_age_seconds"
                ]
            ),
            "maximum_age_seconds": (
                payload[
                    "injected"
                ][
                    "maximum_age_seconds"
                ]
            ),
            "freshness_status_preserved": (
                payload[
                    "injected"
                ][
                    "freshness_status"
                ]
            ),
            "source_sha256": (
                payload[
                    "source_sha256"
                ]
            ),
            "output_sha256": (
                payload[
                    "output_sha256"
                ]
            ),
            "evidence_dir": str(
                args.evidence_dir
            ),
        }
    else:
        summary = {
            "status": "PASS",
            "scenario_id": (
                payload[
                    "scenario_id"
                ]
            ),
            "target_test": (
                payload[
                    "target_test"
                ]
            ),
            "fault_operation": (
                payload[
                    "fault"
                ][
                    "operation"
                ]
            ),
            "baseline_status": (
                payload[
                    "fault"
                ][
                    "status_before"
                ]
            ),
            "injected_status": (
                payload[
                    "fault"
                ][
                    "status_after"
                ]
            ),
            "baseline_failures": (
                payload[
                    "fault"
                ][
                    "failures_before"
                ]
            ),
            "injected_failures": (
                payload[
                    "fault"
                ][
                    "failures_after"
                ]
            ),
            "total_tests": (
                payload[
                    "injected"
                ][
                    "test_results"
                ]
            ),
            "failed_tests": (
                payload[
                    "injected"
                ][
                    "failed_tests"
                ]
            ),
            "source_sha256": (
                payload[
                    "source_sha256"
                ]
            ),
            "output_sha256": (
                payload[
                    "output_sha256"
                ]
            ),
            "evidence_dir": str(
                args.evidence_dir
            ),
        }

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
