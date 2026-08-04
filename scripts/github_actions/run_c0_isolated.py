#!/usr/bin/env python3
"""Run and verify one isolated GitHub Actions C0 pipeline execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import boto3


EXPECTED_BRANCH = "feature/dagster-orchestration"
EXPECTED_ACCOUNT_ID = "522814714524"
EXPECTED_ROLE_NAME = "thesis-pac-dev-github-c0"

EXPECTED_BRONZE_SOURCES = 10
EXPECTED_MODEL_RESULTS = 15
EXPECTED_TEST_RESULTS = 41

EXPECTED_SHADOW_TABLE_COUNTS = {
    "silver": 10,
    "gold_internal": 4,
    "gold_public": 1,
}

CANONICAL_DATABASES = (
    "thesis_pac_dev_silver",
    "thesis_pac_dev_gold_internal",
    "thesis_pac_dev_gold_public",
)

CANONICAL_PREFIXES = (
    "silver/",
    "gold/internal/",
    "gold/public/",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def require_environment(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Required environment variable is missing: {name}"
        )

    return value


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()

    return str(value)


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            default=json_default,
        )
        + "\n"
    ).encode("utf-8")


def write_json(
    destination: Path,
    payload: Any,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        f".{destination.name}.tmp"
    )

    temporary.write_bytes(
        canonical_json_bytes(payload)
    )

    temporary.replace(destination)


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def safe_run_key(value: str) -> str:
    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        value.lower(),
    ).strip("_")

    if not normalized:
        raise RuntimeError(
            "C0 run key is empty after normalization."
        )

    if len(normalized) > 80:
        raise RuntimeError(
            "C0 run key exceeds 80 characters."
        )

    return normalized


def parse_s3_uri(
    uri: str,
) -> tuple[str, str]:
    parsed = urlparse(uri)

    if parsed.scheme != "s3":
        raise RuntimeError(
            f"Expected an S3 URI, found: {uri}"
        )

    bucket = parsed.netloc.strip()
    prefix = parsed.path.lstrip("/")

    if not bucket:
        raise RuntimeError(
            f"S3 URI has no bucket: {uri}"
        )

    return bucket, prefix


def list_glue_tables(
    glue: Any,
    database_name: str,
) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    token: str | None = None

    while True:
        request: dict[str, Any] = {
            "DatabaseName": database_name,
            "MaxResults": 100,
        }

        if token:
            request["NextToken"] = token

        response = glue.get_tables(
            **request
        )

        tables.extend(
            response.get(
                "TableList",
                [],
            )
        )

        token = response.get("NextToken")

        if not token:
            return tables


def normalized_table(
    table: dict[str, Any],
) -> dict[str, Any]:
    descriptor = table.get(
        "StorageDescriptor",
        {},
    )

    serde = descriptor.get(
        "SerdeInfo",
        {},
    )

    return {
        "name": table.get("Name"),
        "table_type": table.get("TableType"),
        "parameters": dict(
            sorted(
                (
                    table.get("Parameters")
                    or {}
                ).items()
            )
        ),
        "partition_keys": [
            {
                "name": column.get("Name"),
                "type": column.get("Type"),
            }
            for column in (
                table.get("PartitionKeys")
                or []
            )
        ],
        "storage": {
            "location": descriptor.get("Location"),
            "input_format": descriptor.get(
                "InputFormat"
            ),
            "output_format": descriptor.get(
                "OutputFormat"
            ),
            "serde_library": serde.get(
                "SerializationLibrary"
            ),
            "columns": [
                {
                    "name": column.get("Name"),
                    "type": column.get("Type"),
                }
                for column in (
                    descriptor.get("Columns")
                    or []
                )
            ],
        },
    }


def list_s3_objects(
    s3: Any,
    *,
    bucket: str,
    prefix: str,
) -> list[dict[str, Any]]:
    paginator = s3.get_paginator(
        "list_objects_v2"
    )

    objects: list[dict[str, Any]] = []

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=prefix,
    ):
        for item in page.get(
            "Contents",
            [],
        ):
            objects.append(
                {
                    "key": item.get("Key"),
                    "size": item.get("Size"),
                    "etag": str(
                        item.get("ETag", "")
                    ).strip('"'),
                    "last_modified": item.get(
                        "LastModified"
                    ),
                    "storage_class": item.get(
                        "StorageClass"
                    ),
                }
            )

    return sorted(
        objects,
        key=lambda item: str(
            item["key"]
        ),
    )


def canonical_snapshot(
    *,
    glue: Any,
    s3: Any,
    data_bucket: str,
) -> dict[str, Any]:
    databases: list[dict[str, Any]] = []

    for database_name in CANONICAL_DATABASES:
        database = glue.get_database(
            Name=database_name
        )["Database"]

        tables = [
            normalized_table(table)
            for table in list_glue_tables(
                glue,
                database_name,
            )
        ]

        databases.append(
            {
                "name": database.get("Name"),
                "location_uri": database.get(
                    "LocationUri"
                ),
                "parameters": dict(
                    sorted(
                        (
                            database.get(
                                "Parameters"
                            )
                            or {}
                        ).items()
                    )
                ),
                "tables": sorted(
                    tables,
                    key=lambda item: str(
                        item["name"]
                    ),
                ),
            }
        )

    prefixes = {
        prefix: list_s3_objects(
            s3,
            bucket=data_bucket,
            prefix=prefix,
        )
        for prefix in CANONICAL_PREFIXES
    }

    payload = {
        "schema_version": 1,
        "glue_databases": databases,
        "s3_bucket": data_bucket,
        "s3_prefixes": prefixes,
    }

    return {
        "sha256": payload_sha256(payload),
        "payload": payload,
    }


def validate_bronze_evidence(
    evidence_root: Path,
) -> dict[str, Any]:
    candidates = sorted(
        evidence_root.rglob(
            "*-bronze-availability.json"
        )
    )

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one Bronze availability "
            f"document, found {len(candidates)}."
        )

    document = json.loads(
        candidates[0].read_text(
            encoding="utf-8"
        )
    )

    payload = document.get(
        "payload",
        {},
    )

    checks = {
        "status_pass": (
            document.get("status")
            == "PASS"
        ),
        "expected_count_10": (
            payload.get("expected_count")
            == EXPECTED_BRONZE_SOURCES
        ),
        "available_count_10": (
            payload.get("available_count")
            == EXPECTED_BRONZE_SOURCES
        ),
        "blocked_count_0": (
            payload.get("blocked_count")
            == 0
        ),
    }

    if not all(checks.values()):
        raise RuntimeError(
            "Bronze availability contract failed."
        )

    return {
        "status": "PASS",
        "path": str(
            candidates[0].relative_to(
                evidence_root
            )
        ),
        "sha256": file_sha256(
            candidates[0]
        ),
        "checks": checks,
    }


def validate_dbt_results(
    run_results_path: Path,
) -> dict[str, Any]:
    if not run_results_path.is_file():
        raise RuntimeError(
            "dbt run_results.json was not produced."
        )

    payload = json.loads(
        run_results_path.read_text(
            encoding="utf-8"
        )
    )

    results = payload.get(
        "results",
        [],
    )

    model_results = [
        result
        for result in results
        if str(
            result.get(
                "unique_id",
                "",
            )
        ).startswith("model.")
    ]

    test_results = [
        result
        for result in results
        if str(
            result.get(
                "unique_id",
                "",
            )
        ).startswith("test.")
    ]

    model_failures = [
        result
        for result in model_results
        if result.get("status")
        != "success"
    ]

    test_failures = [
        result
        for result in test_results
        if result.get("status")
        != "pass"
    ]

    checks = {
        "model_results_15": (
            len(model_results)
            == EXPECTED_MODEL_RESULTS
        ),
        "test_results_41": (
            len(test_results)
            == EXPECTED_TEST_RESULTS
        ),
        "total_results_56": (
            len(results)
            == (
                EXPECTED_MODEL_RESULTS
                + EXPECTED_TEST_RESULTS
            )
        ),
        "model_failures_0": (
            not model_failures
        ),
        "test_failures_0": (
            not test_failures
        ),
    }

    if not all(checks.values()):
        raise RuntimeError(
            "dbt result contract failed."
        )

    return {
        "status": "PASS",
        "total_results": len(results),
        "model_results": len(
            model_results
        ),
        "test_results": len(
            test_results
        ),
        "model_failures": len(
            model_failures
        ),
        "test_failures": len(
            test_failures
        ),
        "elapsed_time_seconds": payload.get(
            "elapsed_time"
        ),
        "checks": checks,
    }


def shadow_inventory(
    *,
    glue: Any,
    s3: Any,
    data_bucket: str,
    results_bucket: str,
    data_root_uri: str,
    results_root_uri: str,
    schemas: dict[str, str],
) -> dict[str, Any]:
    inventories: dict[
        str,
        dict[str, Any],
    ] = {}

    for layer, database_name in schemas.items():
        glue.get_database(
            Name=database_name
        )

        tables = [
            normalized_table(table)
            for table in list_glue_tables(
                glue,
                database_name,
            )
        ]

        expected_count = (
            EXPECTED_SHADOW_TABLE_COUNTS[
                layer
            ]
        )

        if len(tables) != expected_count:
            raise RuntimeError(
                f"{database_name}: expected "
                f"{expected_count} tables, "
                f"found {len(tables)}."
            )

        bad_locations = []

        for table in tables:
            location = (
                table.get(
                    "storage",
                    {},
                ).get("location")
            )

            expected_root = (
                data_root_uri.rstrip("/")
                + "/"
            )

            if (
                not location
                or not str(
                    location
                ).startswith(expected_root)
            ):
                bad_locations.append(
                    {
                        "table": table.get(
                            "name"
                        ),
                        "location": location,
                    }
                )

        if bad_locations:
            raise RuntimeError(
                f"{database_name}: table locations "
                "escaped the isolated C0 root."
            )

        inventories[layer] = {
            "database": database_name,
            "expected_table_count": (
                expected_count
            ),
            "actual_table_count": len(
                tables
            ),
            "tables": sorted(
                tables,
                key=lambda item: str(
                    item["name"]
                ),
            ),
            "bad_locations": bad_locations,
        }

    data_uri_bucket, data_prefix = (
        parse_s3_uri(data_root_uri)
    )

    results_uri_bucket, results_prefix = (
        parse_s3_uri(results_root_uri)
    )

    if data_uri_bucket != data_bucket:
        raise RuntimeError(
            "dbt data-root bucket mismatch."
        )

    if results_uri_bucket != results_bucket:
        raise RuntimeError(
            "Athena results-root bucket mismatch."
        )

    data_objects = list_s3_objects(
        s3,
        bucket=data_bucket,
        prefix=data_prefix,
    )

    result_objects = list_s3_objects(
        s3,
        bucket=results_bucket,
        prefix=results_prefix,
    )

    if not data_objects:
        raise RuntimeError(
            "No isolated C0 data objects found."
        )

    if not result_objects:
        raise RuntimeError(
            "No isolated Athena result objects found."
        )

    return {
        "status": "PASS",
        "layers": inventories,
        "total_tables": sum(
            item["actual_table_count"]
            for item in inventories.values()
        ),
        "data_objects": {
            "bucket": data_bucket,
            "prefix": data_prefix,
            "count": len(data_objects),
            "objects": data_objects,
        },
        "athena_result_objects": {
            "bucket": results_bucket,
            "prefix": results_prefix,
            "count": len(result_objects),
            "objects": result_objects,
        },
    }


def chunks(
    values: list[str],
    size: int,
) -> Iterable[list[str]]:
    for index in range(
        0,
        len(values),
        size,
    ):
        yield values[
            index:index + size
        ]


def athena_query_inventory(
    *,
    athena: Any,
    workgroup: str,
    started_at: datetime,
    completed_at: datetime,
    schema_names: Iterable[str],
) -> dict[str, Any]:
    query_ids: list[str] = []
    token: str | None = None

    while True:
        request: dict[str, Any] = {
            "WorkGroup": workgroup,
            "MaxResults": 50,
        }

        if token:
            request["NextToken"] = token

        response = (
            athena.list_query_executions(
                **request
            )
        )

        query_ids.extend(
            response.get(
                "QueryExecutionIds",
                [],
            )
        )

        token = response.get("NextToken")

        if not token:
            break

    executions: list[
        dict[str, Any]
    ] = []

    for query_batch in chunks(
        query_ids,
        50,
    ):
        response = (
            athena.batch_get_query_execution(
                QueryExecutionIds=query_batch
            )
        )

        executions.extend(
            response.get(
                "QueryExecutions",
                [],
            )
        )

    lower_bound = (
        started_at
        - timedelta(seconds=60)
    )

    upper_bound = (
        completed_at
        + timedelta(seconds=60)
    )

    schema_markers = tuple(
        schema_names
    )

    matched = []

    for execution in executions:
        status = execution.get(
            "Status",
            {},
        )

        submitted = status.get(
            "SubmissionDateTime"
        )

        if not isinstance(
            submitted,
            datetime,
        ):
            continue

        submitted_utc = (
            submitted.astimezone(
                timezone.utc
            )
        )

        if not (
            lower_bound
            <= submitted_utc
            <= upper_bound
        ):
            continue

        query = str(
            execution.get(
                "Query",
                "",
            )
        )

        database = str(
            execution.get(
                "QueryExecutionContext",
                {},
            ).get(
                "Database",
                "",
            )
        )

        attributed = (
            database in schema_markers
            or any(
                marker in query
                for marker in schema_markers
            )
        )

        if not attributed:
            continue

        matched.append(
            {
                "query_execution_id": (
                    execution.get(
                        "QueryExecutionId"
                    )
                ),
                "state": status.get(
                    "State"
                ),
                "submission_time": (
                    submitted_utc
                ),
                "completion_time": status.get(
                    "CompletionDateTime"
                ),
                "database": database,
                "data_scanned_bytes": (
                    execution.get(
                        "Statistics",
                        {},
                    ).get(
                        "DataScannedInBytes"
                    )
                ),
                "engine_execution_time_ms": (
                    execution.get(
                        "Statistics",
                        {},
                    ).get(
                        "EngineExecutionTimeInMillis"
                    )
                ),
                "query": query,
            }
        )

    if not matched:
        raise RuntimeError(
            "No Athena queries were attributed "
            "to the isolated C0 schemas."
        )

    failed = [
        item
        for item in matched
        if item["state"] != "SUCCEEDED"
    ]

    if failed:
        raise RuntimeError(
            "One or more isolated C0 Athena "
            "queries did not succeed."
        )

    return {
        "status": "PASS",
        "workgroup": workgroup,
        "query_count": len(matched),
        "failed_query_count": 0,
        "queries": sorted(
            matched,
            key=lambda item: str(
                item[
                    "query_execution_id"
                ]
            ),
        ),
    }


def copy_dbt_artifacts(
    *,
    repository_root: Path,
    evidence_root: Path,
) -> None:
    destination = (
        evidence_root
        / "dbt"
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = {
        (
            repository_root
            / "transformations"
            / "dbt"
            / "target"
            / "manifest.json"
        ): destination / "manifest.json",
        (
            repository_root
            / "transformations"
            / "dbt"
            / "target"
            / "run_results.json"
        ): destination / "run_results.json",
        (
            repository_root
            / "transformations"
            / "dbt"
            / "logs"
            / "dbt.log"
        ): destination / "dbt.log",
    }

    for source, target in candidates.items():
        if source.is_file():
            shutil.copy2(
                source,
                target,
            )


def create_checksums(
    evidence_root: Path,
) -> str:
    files = sorted(
        path
        for path in evidence_root.rglob("*")
        if (
            path.is_file()
            and path.name != "SHA256SUMS"
        )
    )

    lines = []

    for path in files:
        relative = path.relative_to(
            evidence_root
        )

        lines.append(
            f"{file_sha256(path)}  "
            f"{relative.as_posix()}"
        )

    manifest = (
        evidence_root
        / "SHA256SUMS"
    )

    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return file_sha256(manifest)


def execute(
    evidence_root: Path,
) -> dict[str, Any]:
    repository_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    branch = require_environment(
        "THESIS_GIT_BRANCH"
    )

    commit = require_environment(
        "THESIS_GIT_COMMIT"
    )

    condition = require_environment(
        "THESIS_EXPERIMENT_CONDITION"
    )

    scenario = require_environment(
        "THESIS_SCENARIO_ID"
    )

    run_key = safe_run_key(
        require_environment(
            "C0_RUN_KEY"
        )
    )

    data_bucket = require_environment(
        "DATA_LAKE_BUCKET"
    )

    results_bucket = require_environment(
        "ATHENA_RESULTS_BUCKET"
    )

    workgroup = require_environment(
        "DBT_ATHENA_WORKGROUP"
    )

    data_root_uri = require_environment(
        "DBT_ATHENA_DATA_DIR"
    )

    results_root_uri = require_environment(
        "DBT_ATHENA_STAGING_DIR"
    )

    schemas = {
        "silver": require_environment(
            "DBT_ATHENA_SCHEMA"
        ),
        "gold_internal": require_environment(
            "DBT_GOLD_INTERNAL_SCHEMA"
        ),
        "gold_public": require_environment(
            "DBT_GOLD_PUBLIC_SCHEMA"
        ),
    }

    if branch != EXPECTED_BRANCH:
        raise RuntimeError(
            f"Unexpected Git branch: {branch}"
        )

    if condition != "C0":
        raise RuntimeError(
            f"Unexpected condition: {condition}"
        )

    if scenario != "baseline":
        raise RuntimeError(
            f"Unexpected scenario: {scenario}"
        )

    if len(set(schemas.values())) != 3:
        raise RuntimeError(
            "Shadow schemas are not unique."
        )

    if not all(
        name.startswith(
            "thesis_pac_c0_"
        )
        for name in schemas.values()
    ):
        raise RuntimeError(
            "A shadow schema escaped the C0 prefix."
        )

    expected_data_root = (
        f"s3://{data_bucket}/experiments/c0/"
    )

    expected_results_root = (
        f"s3://{results_bucket}/experiments/c0/"
    )

    if not data_root_uri.startswith(
        expected_data_root
    ):
        raise RuntimeError(
            "C0 data root escaped its S3 boundary."
        )

    if not results_root_uri.startswith(
        expected_results_root
    ):
        raise RuntimeError(
            "Athena results escaped their S3 boundary."
        )

    evidence_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json(
        evidence_root
        / "run-context.json",
        {
            "status": "RUNNING",
            "started_at_utc": utc_now(),
            "condition": condition,
            "scenario": scenario,
            "branch": branch,
            "commit": commit,
            "run_key": run_key,
            "github": {
                "repository": os.getenv(
                    "GITHUB_REPOSITORY"
                ),
                "workflow": os.getenv(
                    "GITHUB_WORKFLOW"
                ),
                "run_id": os.getenv(
                    "GITHUB_RUN_ID"
                ),
                "run_attempt": os.getenv(
                    "GITHUB_RUN_ATTEMPT"
                ),
                "ref": os.getenv(
                    "GITHUB_REF"
                ),
                "sha": os.getenv(
                    "GITHUB_SHA"
                ),
            },
            "schemas": schemas,
            "data_root_uri": data_root_uri,
            "results_root_uri": results_root_uri,
            "pac_active": False,
            "self_healing_active": False,
            "automatic_remediation_active": False,
        },
    )

    sts = boto3.client("sts")
    glue = boto3.client("glue")
    s3 = boto3.client("s3")
    athena = boto3.client("athena")

    identity = sts.get_caller_identity()
    identity_arn = str(
        identity.get("Arn", "")
    )

    identity_checks = {
        "account_matches": (
            identity.get("Account")
            == EXPECTED_ACCOUNT_ID
        ),
        "assumed_role_matches": (
            (
                ":assumed-role/"
                f"{EXPECTED_ROLE_NAME}/"
            )
            in identity_arn
        ),
        "permanent_user_absent": (
            ":user/" not in identity_arn
        ),
    }

    if not all(
        identity_checks.values()
    ):
        raise RuntimeError(
            "OIDC caller identity validation failed."
        )

    write_json(
        evidence_root
        / "oidc-caller-identity.json",
        {
            "status": "PASS",
            "identity": identity,
            "checks": identity_checks,
            "permanent_aws_access_keys": False,
        },
    )

    before = canonical_snapshot(
        glue=glue,
        s3=s3,
        data_bucket=data_bucket,
    )

    write_json(
        evidence_root
        / "canonical-before.json",
        before,
    )

    execution_started = (
        datetime.now(timezone.utc)
    )

    monotonic_started = time.monotonic()

    result = None
    execution_error: BaseException | None = None

    try:
        from thesis_orchestration import defs

        job = defs.resolve_job_def(
            "bronze_silver_gold_job"
        )

        result = job.execute_in_process(
            raise_on_error=False
        )

    except BaseException as error:
        execution_error = error

    execution_completed = (
        datetime.now(timezone.utc)
    )

    runtime_seconds = (
        time.monotonic()
        - monotonic_started
    )

    after = canonical_snapshot(
        glue=glue,
        s3=s3,
        data_bucket=data_bucket,
    )

    write_json(
        evidence_root
        / "canonical-after.json",
        after,
    )

    canonical_changed = (
        before["sha256"]
        != after["sha256"]
    )

    comparison = {
        "status": (
            "FAIL"
            if canonical_changed
            else "PASS"
        ),
        "before_sha256": before["sha256"],
        "after_sha256": after["sha256"],
        "changed": canonical_changed,
        "canonical_glue_changes": (
            "UNKNOWN_NONZERO"
            if canonical_changed
            else 0
        ),
        "canonical_s3_changes": (
            "UNKNOWN_NONZERO"
            if canonical_changed
            else 0
        ),
    }

    write_json(
        evidence_root
        / "canonical-comparison.json",
        comparison,
    )

    if canonical_changed:
        raise RuntimeError(
            "Canonical Silver or Gold changed."
        )

    if execution_error is not None:
        raise execution_error

    if result is None:
        raise RuntimeError(
            "Dagster returned no result."
        )

    if not result.success:
        raise RuntimeError(
            "bronze_silver_gold_job failed."
        )

    write_json(
        evidence_root
        / "dagster-summary.json",
        {
            "status": "PASS",
            "job_name": (
                "bronze_silver_gold_job"
            ),
            "run_id": getattr(
                result,
                "run_id",
                None,
            ),
            "success": result.success,
            "event_count": len(
                getattr(
                    result,
                    "all_events",
                    [],
                )
            ),
            "runtime_seconds": round(
                runtime_seconds,
                6,
            ),
        },
    )

    bronze_summary = (
        validate_bronze_evidence(
            evidence_root
        )
    )

    write_json(
        evidence_root
        / "bronze-summary.json",
        bronze_summary,
    )

    run_results_path = (
        repository_root
        / "transformations"
        / "dbt"
        / "target"
        / "run_results.json"
    )

    dbt_summary = validate_dbt_results(
        run_results_path
    )

    write_json(
        evidence_root
        / "dbt-summary.json",
        dbt_summary,
    )

    isolated_inventory = shadow_inventory(
        glue=glue,
        s3=s3,
        data_bucket=data_bucket,
        results_bucket=results_bucket,
        data_root_uri=data_root_uri,
        results_root_uri=results_root_uri,
        schemas=schemas,
    )

    write_json(
        evidence_root
        / "isolated-inventory.json",
        isolated_inventory,
    )

    query_inventory = athena_query_inventory(
        athena=athena,
        workgroup=workgroup,
        started_at=execution_started,
        completed_at=execution_completed,
        schema_names=schemas.values(),
    )

    write_json(
        evidence_root
        / "athena-query-inventory.json",
        query_inventory,
    )

    copy_dbt_artifacts(
        repository_root=repository_root,
        evidence_root=evidence_root,
    )

    checkpoint = {
        "status": "PASS",
        "checkpoint": (
            "GITHUB_ACTIONS_C0_ATOMIC_RUN"
        ),
        "condition": "C0",
        "scenario": "baseline",
        "branch": branch,
        "commit": commit,
        "github_run_id": os.getenv(
            "GITHUB_RUN_ID"
        ),
        "github_run_attempt": os.getenv(
            "GITHUB_RUN_ATTEMPT"
        ),
        "oidc_exchange": "PASS",
        "caller_identity": {
            "account": identity.get(
                "Account"
            ),
            "arn": identity_arn,
            "permanent_access_keys": False,
        },
        "bronze": {
            "expected": 10,
            "available": 10,
            "blocked": 0,
        },
        "dagster": {
            "job": (
                "bronze_silver_gold_job"
            ),
            "status": "PASS",
            "runtime_seconds": round(
                runtime_seconds,
                6,
            ),
        },
        "dbt": {
            "materialized_models": 15,
            "tests": 41,
            "failures": 0,
        },
        "isolated_outputs": {
            "silver_tables": 10,
            "gold_internal_tables": 4,
            "gold_public_tables": 1,
            "total_tables": (
                isolated_inventory[
                    "total_tables"
                ]
            ),
            "data_root": data_root_uri,
            "athena_results_root": (
                results_root_uri
            ),
        },
        "canonical_protection": {
            "before_sha256": before[
                "sha256"
            ],
            "after_sha256": after[
                "sha256"
            ],
            "changed": False,
            "glue_changes": 0,
            "s3_changes": 0,
        },
        "experiment_controls": {
            "pac_active": False,
            "opa_conftest_active": False,
            "self_healing_active": False,
            "automatic_remediation_active": False,
        },
        "athena": {
            "workgroup": workgroup,
            "query_count": query_inventory[
                "query_count"
            ],
            "failed_queries": 0,
        },
        "evidence_manifest": "SHA256SUMS",
    }

    write_json(
        evidence_root
        / "final-checkpoint.json",
        checkpoint,
    )

    manifest_sha256 = create_checksums(
        evidence_root
    )

    print(
        json.dumps(
            checkpoint,
            indent=2,
            sort_keys=True,
        )
    )

    print(
        "Evidence manifest SHA-256: "
        f"{manifest_sha256}"
    )

    return checkpoint


def self_test(
    output_path: Path,
) -> None:
    first = {
        "b": 2,
        "a": 1,
    }

    second = {
        "a": 1,
        "b": 2,
    }

    with tempfile.TemporaryDirectory() as root:
        evidence_root = Path(root)

        write_json(
            evidence_root
            / "test.json",
            first,
        )

        checksum = create_checksums(
            evidence_root
        )

        checks = {
            "stable_payload_hash": (
                payload_sha256(first)
                == payload_sha256(second)
            ),
            "safe_run_key": (
                safe_run_key(
                    "GHA-123-1"
                )
                == "gha_123_1"
            ),
            "json_written": (
                (
                    evidence_root
                    / "test.json"
                ).is_file()
            ),
            "checksum_written": (
                (
                    evidence_root
                    / "SHA256SUMS"
                ).is_file()
            ),
            "checksum_length_64": (
                len(checksum) == 64
            ),
            "canonical_database_count_3": (
                len(CANONICAL_DATABASES)
                == 3
            ),
            "canonical_prefix_count_3": (
                len(CANONICAL_PREFIXES)
                == 3
            ),
            "shadow_table_total_15": (
                sum(
                    EXPECTED_SHADOW_TABLE_COUNTS.values()
                )
                == 15
            ),
        }

    status = (
        "PASS"
        if all(checks.values())
        else "FAIL"
    )

    result = {
        "status": status,
        "aws_calls": False,
        "dagster_execution": False,
        "dbt_execution": False,
        "checks": checks,
    }

    write_json(
        output_path,
        result,
    )

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )

    if status != "PASS":
        raise SystemExit(
            "C0 runner self-test failed."
        )


def main() -> int:
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    self_test_parser = subparsers.add_parser(
        "self-test"
    )

    self_test_parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    execute_parser = subparsers.add_parser(
        "execute"
    )

    execute_parser.add_argument(
        "--evidence-root",
        type=Path,
        required=True,
    )

    arguments = parser.parse_args()

    if arguments.command == "self-test":
        self_test(
            arguments.output.resolve()
        )
        return 0

    evidence_root = (
        arguments.evidence_root
        .expanduser()
        .resolve()
    )

    try:
        execute(evidence_root)
        return 0

    except BaseException as error:
        evidence_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        write_json(
            evidence_root
            / "failure.json",
            {
                "status": "FAIL",
                "recorded_at_utc": utc_now(),
                "error_type": (
                    type(error).__name__
                ),
                "error": str(error),
                "traceback": traceback.format_exc(),
            },
        )

        repository_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        copy_dbt_artifacts(
            repository_root=repository_root,
            evidence_root=evidence_root,
        )

        create_checksums(
            evidence_root
        )

        raise


if __name__ == "__main__":
    sys.exit(main())
