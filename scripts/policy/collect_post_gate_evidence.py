#!/usr/bin/env python3
"""Collect normalized post-execution evidence for the C1 policy gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class EvidenceError(RuntimeError):
    """Raised when execution evidence cannot be normalized safely."""


STATIC_SECTIONS = (
    "metadata",
    "schema_contract",
    "transformation",
    "privacy",
)

FRESHNESS_COLUMNS = {
    "dataset_name",
    "expected_publish_time",
    "actual_publish_time",
    "freshness_slo_hours",
    "freshness_status",
    "run_id",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise EvidenceError(
            f"Unable to read JSON evidence {path}: {error}"
        ) from error


def require_mapping(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(
            f"{label} must be a JSON object."
        )

    return value


def nonnegative_integer(
    value: Any,
    *,
    label: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise EvidenceError(
            f"{label} must be a non-negative integer."
        )

    return value


def parse_timestamp(
    value: str,
    *,
    label: str,
) -> datetime:
    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as error:
        raise EvidenceError(
            f"Invalid ISO timestamp for {label}: {value}"
        ) from error


def canonical_bytes(
    payload: Any,
) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def write_json(
    path: Path,
    payload: Any,
) -> str:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    encoded = canonical_bytes(
        payload
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(
            handle.name
        )
        handle.write(
            encoded
        )
        handle.flush()

    temporary.replace(
        path
    )

    return sha256_bytes(
        encoded
    )


def normalize_quality(
    run_results_path: Path,
) -> dict[str, Any]:
    payload = require_mapping(
        load_json(
            run_results_path
        ),
        label="dbt run_results",
    )

    results = payload.get(
        "results"
    )

    if not isinstance(
        results,
        list,
    ):
        raise EvidenceError(
            "dbt run_results.results must be an array."
        )

    tests = [
        result
        for result in results
        if (
            isinstance(
                result,
                dict,
            )
            and str(
                result.get(
                    "unique_id",
                    "",
                )
            ).startswith(
                "test."
            )
        )
    ]

    failures = [
        result
        for result in tests
        if result.get(
            "status"
        ) != "pass"
    ]

    critical_failures = sorted({
        str(
            result.get(
                "unique_id",
                "__unknown_test__",
            )
        )
        for result in failures
    })

    return {
        "status": (
            "FAIL"
            if failures
            else "PASS"
        ),
        "total_tests": len(
            tests
        ),
        "failed_tests": len(
            failures
        ),
        "critical_failures": (
            critical_failures
        ),
    }


def normalize_freshness(
    freshness_control_path: Path,
) -> dict[str, Any]:
    try:
        with freshness_control_path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            reader = csv.DictReader(
                handle
            )

            columns = set(
                reader.fieldnames
                or []
            )

            missing = (
                FRESHNESS_COLUMNS
                - columns
            )

            if missing:
                raise EvidenceError(
                    "Freshness control is missing "
                    f"columns: {sorted(missing)}"
                )

            rows = list(
                reader
            )

    except OSError as error:
        raise EvidenceError(
            "Unable to read freshness control "
            f"{freshness_control_path}: {error}"
        ) from error

    if not rows:
        raise EvidenceError(
            "Freshness control contains no rows."
        )

    sources: list[
        dict[str, Any]
    ] = []

    seen_sources: set[
        str
    ] = set()

    for row in rows:
        source = str(
            row.get(
                "dataset_name",
                "",
            )
        ).strip()

        if not source:
            raise EvidenceError(
                "Freshness dataset_name must not be empty."
            )

        if source in seen_sources:
            raise EvidenceError(
                f"Duplicate freshness dataset: {source}"
            )

        seen_sources.add(
            source
        )

        status = str(
            row.get(
                "freshness_status",
                "",
            )
        ).strip().upper()

        if status not in {
            "PASS",
            "FAIL",
        }:
            raise EvidenceError(
                "freshness_status must be PASS or FAIL "
                f"for {source}; got {status!r}."
            )

        actual = parse_timestamp(
            str(
                row[
                    "actual_publish_time"
                ]
            ),
            label=(
                f"{source}.actual_publish_time"
            ),
        )

        expected = parse_timestamp(
            str(
                row[
                    "expected_publish_time"
                ]
            ),
            label=(
                f"{source}.expected_publish_time"
            ),
        )

        try:
            slo_hours = float(
                row[
                    "freshness_slo_hours"
                ]
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise EvidenceError(
                "freshness_slo_hours must be numeric "
                f"for {source}."
            ) from error

        if slo_hours < 0:
            raise EvidenceError(
                "freshness_slo_hours must be non-negative "
                f"for {source}."
            )

        observed_age_seconds = max(
            0.0,
            (
                expected
                - actual
            ).total_seconds(),
        )

        maximum_age_seconds = (
            slo_hours
            * 3600.0
        )

        normalized_status = (
            "FAIL"
            if (
                status == "FAIL"
                or observed_age_seconds
                > maximum_age_seconds
            )
            else "PASS"
        )

        sources.append({
            "source": source,
            "observed_age_seconds": (
                observed_age_seconds
            ),
            "maximum_age_seconds": (
                maximum_age_seconds
            ),
            "status": normalized_status,
        })

    sources.sort(
        key=lambda item: item[
            "source"
        ]
    )

    aggregate_status = (
        "FAIL"
        if any(
            source["status"]
            == "FAIL"
            for source in sources
        )
        else "PASS"
    )

    return {
        "status": aggregate_status,
        "sources": sources,
    }


def normalize_runtime(
    *,
    dagster_summary_path: Path,
    canonical_comparison_path: Path,
    isolated_inventory_path: Path,
    athena_query_inventory_path: Path,
) -> dict[str, Any]:
    dagster = require_mapping(
        load_json(
            dagster_summary_path
        ),
        label="Dagster summary",
    )

    canonical = require_mapping(
        load_json(
            canonical_comparison_path
        ),
        label="canonical comparison",
    )

    isolated = require_mapping(
        load_json(
            isolated_inventory_path
        ),
        label="isolated inventory",
    )

    athena = require_mapping(
        load_json(
            athena_query_inventory_path
        ),
        label="Athena query inventory",
    )

    dagster_pass = (
        dagster.get(
            "status"
        )
        == "PASS"
        and dagster.get(
            "success"
        )
        is True
    )

    canonical_unchanged = (
        canonical.get(
            "status"
        )
        == "PASS"
        and canonical.get(
            "changed"
        )
        is False
    )

    isolated_output_tables = (
        nonnegative_integer(
            isolated.get(
                "total_tables"
            ),
            label=(
                "isolated_inventory.total_tables"
            ),
        )
    )

    athena_failed_queries = (
        nonnegative_integer(
            athena.get(
                "failed_query_count"
            ),
            label=(
                "athena_query_inventory."
                "failed_query_count"
            ),
        )
    )

    return {
        "pipeline_status": (
            "PASS"
            if dagster_pass
            else "FAIL"
        ),
        "canonical_unchanged": (
            canonical_unchanged
        ),
        "isolated_output_tables": (
            isolated_output_tables
        ),
        "athena_failed_queries": (
            athena_failed_queries
        ),
    }


def collect_post_evidence(
    *,
    pre_evidence_path: Path,
    run_results_path: Path,
    dagster_summary_path: Path,
    canonical_comparison_path: Path,
    isolated_inventory_path: Path,
    athena_query_inventory_path: Path,
    freshness_control_path: Path,
) -> dict[str, Any]:
    pre = require_mapping(
        load_json(
            pre_evidence_path
        ),
        label="pre-gate evidence",
    )

    missing = [
        section
        for section in STATIC_SECTIONS
        if section not in pre
    ]

    if missing:
        raise EvidenceError(
            "Pre-gate evidence is missing "
            f"sections: {missing}"
        )

    payload = {
        section: pre[
            section
        ]
        for section in STATIC_SECTIONS
    }

    payload[
        "quality"
    ] = normalize_quality(
        run_results_path
    )

    payload[
        "freshness"
    ] = normalize_freshness(
        freshness_control_path
    )

    payload[
        "runtime"
    ] = normalize_runtime(
        dagster_summary_path=(
            dagster_summary_path
        ),
        canonical_comparison_path=(
            canonical_comparison_path
        ),
        isolated_inventory_path=(
            isolated_inventory_path
        ),
        athena_query_inventory_path=(
            athena_query_inventory_path
        ),
    )

    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Collect normalized C1 post-execution "
            "evidence from isolated pipeline artifacts."
        )
    )

    result.add_argument(
        "--pre-evidence",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--run-results",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--dagster-summary",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--canonical-comparison",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--isolated-inventory",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--athena-query-inventory",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--freshness-control",
        required=True,
        type=Path,
    )

    result.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return result


def main() -> int:
    args = parser().parse_args()

    try:
        evidence = collect_post_evidence(
            pre_evidence_path=(
                args.pre_evidence
            ),
            run_results_path=(
                args.run_results
            ),
            dagster_summary_path=(
                args.dagster_summary
            ),
            canonical_comparison_path=(
                args.canonical_comparison
            ),
            isolated_inventory_path=(
                args.isolated_inventory
            ),
            athena_query_inventory_path=(
                args.athena_query_inventory
            ),
            freshness_control_path=(
                args.freshness_control
            ),
        )

        digest = write_json(
            args.output,
            evidence,
        )

    except EvidenceError as error:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": str(
                        error
                    ),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )

        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(
                    args.output
                ),
                "sha256": digest,
                "quality": evidence[
                    "quality"
                ][
                    "status"
                ],
                "freshness": evidence[
                    "freshness"
                ][
                    "status"
                ],
                "runtime": evidence[
                    "runtime"
                ][
                    "pipeline_status"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
