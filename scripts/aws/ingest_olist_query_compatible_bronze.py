#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_MANIFEST_SHA256 = (
    "ba7579a17f904fe60b7fbbb14186ff38"
    "962030af419014d7593eeabefb2d14d9"
)

EXPECTED_SOURCE_SNAPSHOT_ID = (
    "43cc5e9c8436f7919491dd90872d6f4d"
    "94d61d4694c1d4307e41456e405052d2"
)

EXPECTED_GENERATED_SNAPSHOT_ID = (
    "921334afa3174398562e25bf51a14b8b"
    "74692b64053d1f8728dec259ac93b5c5"
)

EXPECTED_DATASET_COUNT = 9
EXPECTED_TOTAL_ROWS = 1550922
EXPECTED_TOTAL_BYTES = 314973186
EXPECTED_MULTILINE_RECORDS = 3852

EXPECTED_TABLES = [
    "olist_customers",
    "olist_geolocation",
    "olist_order_items",
    "olist_order_payments",
    "olist_order_reviews",
    "olist_orders",
    "olist_products",
    "olist_sellers",
    "olist_product_category_name_translation",
]

EXPECTED_SERDE_LIBRARY = (
    "org.apache.hive.hcatalog.data.JsonSerDe"
)

EXPECTED_INPUT_FORMAT = (
    "org.apache.hadoop.mapred.TextInputFormat"
)

EXPECTED_OUTPUT_FORMAT = (
    "org.apache.hadoop.hive.ql.io."
    "HiveIgnoreKeyTextOutputFormat"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Checksum-verified and idempotent upload "
            "of the deterministic Olist "
            "query-compatible Bronze snapshot."
        )
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "manifests/bronze/olist/"
            "query-compatible-manifest.json"
        ),
    )

    parser.add_argument(
        "--generated-root",
        type=Path,
        required=True,
        help=(
            "Local generated snapshot directory "
            "containing tables/<table>/data.jsonl."
        ),
    )

    parser.add_argument(
        "--bucket",
        required=True,
    )

    parser.add_argument(
        "--account-id",
        required=True,
    )

    parser.add_argument(
        "--region",
        required=True,
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Perform S3 writes. Without this flag, "
            "the script is strictly read-only."
        ),
    )

    parser.add_argument(
        "--confirm-generated-snapshot-id",
        help=(
            "Required with --execute and must match "
            "the generated snapshot ID exactly."
        ),
    )

    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(
            "evidence/"
            "bronze-query-compatible-ingestion"
        ),
    )

    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def iso_utc(
    value: datetime,
) -> str:
    return value.isoformat().replace(
        "+00:00",
        "Z",
    )


def run(
    command: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): "
            f"{' '.join(command)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def run_json(
    command: list[str],
) -> dict[str, Any]:
    result = run(command)

    try:
        return json.loads(
            result.stdout
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Command returned invalid JSON: "
            f"{' '.join(command)}\n"
            f"Output:\n{result.stdout}"
        ) from exc


def aws_s3_command(
    operation: str,
    *arguments: str,
    account_id: str,
    region: str,
) -> list[str]:
    return [
        "aws",
        "s3api",
        operation,
        *arguments,
        "--expected-bucket-owner",
        account_id,
        "--region",
        region,
        "--output",
        "json",
        "--no-cli-pager",
    ]


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_base64(
    sha256_hex: str,
) -> str:
    return base64.b64encode(
        bytes.fromhex(
            sha256_hex
        )
    ).decode("ascii")


def validate_jsonl(
    *,
    path: Path,
    expected_rows: int,
    expected_columns: list[str],
) -> None:
    observed_rows = 0

    with path.open(
        "rb"
    ) as handle:
        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            if not line.endswith(
                b"\n"
            ):
                raise RuntimeError(
                    f"{path} line {line_number} "
                    "does not end with LF."
                )

            payload = line[:-1]

            if (
                b"\r" in payload
                or b"\n" in payload
            ):
                raise RuntimeError(
                    f"{path} line {line_number} "
                    "contains a physical embedded "
                    "line break."
                )

            try:
                record = json.loads(
                    payload.decode("utf-8")
                )
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                raise RuntimeError(
                    f"Invalid JSONL record in "
                    f"{path}, line {line_number}."
                ) from exc

            if (
                list(record)
                != expected_columns
            ):
                raise RuntimeError(
                    f"Column order mismatch in "
                    f"{path}, line {line_number}."
                )

            if not all(
                isinstance(value, str)
                for value in record.values()
            ):
                raise RuntimeError(
                    f"Non-string field value in "
                    f"{path}, line {line_number}."
                )

            observed_rows += 1

    if observed_rows != expected_rows:
        raise RuntimeError(
            f"Row-count mismatch for {path}: "
            f"expected {expected_rows}, "
            f"observed {observed_rows}."
        )


def validate_manifest(
    *,
    manifest_path: Path,
    generated_root: Path,
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise RuntimeError(
            "Manifest does not exist: "
            f"{manifest_path}"
        )

    observed_manifest_hash = (
        sha256_file(
            manifest_path
        )
    )

    if (
        observed_manifest_hash
        != EXPECTED_MANIFEST_SHA256
    ):
        raise RuntimeError(
            "Unexpected generated manifest "
            "SHA-256: "
            f"{observed_manifest_hash}"
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    if (
        manifest.get(
            "source_snapshot_id"
        )
        != EXPECTED_SOURCE_SNAPSHOT_ID
    ):
        raise RuntimeError(
            "Unexpected source snapshot ID."
        )

    if (
        manifest.get(
            "generated_snapshot_id"
        )
        != EXPECTED_GENERATED_SNAPSHOT_ID
    ):
        raise RuntimeError(
            "Unexpected generated snapshot ID."
        )

    if (
        generated_root.name
        != EXPECTED_GENERATED_SNAPSHOT_ID
    ):
        raise RuntimeError(
            "Generated root directory name "
            "does not match the generated "
            "snapshot ID."
        )

    if (
        manifest.get(
            "dataset_count"
        )
        != EXPECTED_DATASET_COUNT
    ):
        raise RuntimeError(
            "Expected exactly nine datasets."
        )

    if (
        manifest.get(
            "total_data_rows"
        )
        != EXPECTED_TOTAL_ROWS
    ):
        raise RuntimeError(
            "Unexpected total row count."
        )

    if (
        manifest.get(
            "total_output_size_bytes"
        )
        != EXPECTED_TOTAL_BYTES
    ):
        raise RuntimeError(
            "Unexpected total generated bytes."
        )

    if (
        manifest.get(
            "total_records_with_embedded_breaks"
        )
        != EXPECTED_MULTILINE_RECORDS
    ):
        raise RuntimeError(
            "Unexpected preserved multiline "
            "record count."
        )

    if (
        manifest.get("representation")
        != "athena-json-lines"
    ):
        raise RuntimeError(
            "Unexpected representation."
        )

    serde = manifest.get(
        "serde",
        {},
    )

    if serde != {
        "library": EXPECTED_SERDE_LIBRARY,
        "input_format": EXPECTED_INPUT_FORMAT,
        "output_format": EXPECTED_OUTPUT_FORMAT,
    }:
        raise RuntimeError(
            "Unexpected SerDe configuration."
        )

    destination_prefix = (
        "bronze/generated/olist/"
        "query-compatible/snapshots/"
        f"{EXPECTED_GENERATED_SNAPSHOT_ID}"
    )

    if (
        manifest.get(
            "destination_prefix"
        )
        != destination_prefix
    ):
        raise RuntimeError(
            "Unexpected destination prefix."
        )

    expected_manifest_key = (
        f"{destination_prefix}/"
        "query-compatible-manifest.json"
    )

    if (
        manifest.get(
            "manifest_destination_key"
        )
        != expected_manifest_key
    ):
        raise RuntimeError(
            "Unexpected completion-manifest key."
        )

    datasets = manifest.get(
        "datasets",
        [],
    )

    table_names = [
        dataset["table_name"]
        for dataset in datasets
    ]

    if table_names != EXPECTED_TABLES:
        raise RuntimeError(
            "Unexpected generated table set "
            "or ordering."
        )

    total_rows = 0
    total_bytes = 0

    for dataset in datasets:
        table_name = dataset[
            "table_name"
        ]

        expected_relative_path = (
            Path("tables")
            / table_name
            / "data.jsonl"
        )

        relative_path = Path(
            dataset[
                "local_relative_path"
            ]
        )

        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise RuntimeError(
                "Generated local path must be "
                "repository-independent and "
                "relative."
            )

        if (
            relative_path
            != expected_relative_path
        ):
            raise RuntimeError(
                "Unexpected local relative path "
                f"for {table_name}."
            )

        local_path = (
            generated_root
            / relative_path
        )

        if not local_path.is_file():
            raise RuntimeError(
                f"Missing generated file: "
                f"{local_path}"
            )

        expected_key = (
            f"{destination_prefix}/"
            f"tables/{table_name}/"
            "data.jsonl"
        )

        if (
            dataset.get(
                "destination_key"
            )
            != expected_key
        ):
            raise RuntimeError(
                "Unexpected destination key "
                f"for {table_name}."
            )

        expected_location = (
            "s3://${data_lake_bucket}/"
            f"{destination_prefix}/"
            f"tables/{table_name}/"
        )

        if (
            dataset.get(
                "destination_location"
            )
            != expected_location
        ):
            raise RuntimeError(
                "Unexpected table location "
                f"for {table_name}."
            )

        observed_size = (
            local_path.stat().st_size
        )

        observed_hash = (
            sha256_file(
                local_path
            )
        )

        if (
            observed_size
            != dataset[
                "output_size_bytes"
            ]
        ):
            raise RuntimeError(
                "Generated byte-size mismatch "
                f"for {table_name}."
            )

        if (
            observed_hash
            != dataset[
                "output_sha256"
            ]
        ):
            raise RuntimeError(
                "Generated SHA-256 mismatch "
                f"for {table_name}."
            )

        columns = [
            column["name"]
            for column in dataset[
                "columns"
            ]
        ]

        if not columns:
            raise RuntimeError(
                f"No columns defined for "
                f"{table_name}."
            )

        if not all(
            column["type"] == "string"
            for column in dataset[
                "columns"
            ]
        ):
            raise RuntimeError(
                f"All Bronze columns must be "
                f"string for {table_name}."
            )

        validate_jsonl(
            path=local_path,
            expected_rows=(
                dataset["row_count"]
            ),
            expected_columns=columns,
        )

        total_rows += dataset[
            "row_count"
        ]

        total_bytes += dataset[
            "output_size_bytes"
        ]

    if total_rows != EXPECTED_TOTAL_ROWS:
        raise RuntimeError(
            "Calculated generated row total "
            "does not match the manifest."
        )

    if total_bytes != EXPECTED_TOTAL_BYTES:
        raise RuntimeError(
            "Calculated generated byte total "
            "does not match the manifest."
        )

    return manifest


def head_object(
    *,
    bucket: str,
    key: str,
    account_id: str,
    region: str,
) -> dict[str, Any] | None:
    result = run(
        aws_s3_command(
            "head-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--checksum-mode",
            "ENABLED",
            account_id=account_id,
            region=region,
        ),
        check=False,
    )

    if result.returncode == 0:
        try:
            return json.loads(
                result.stdout
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "HeadObject returned invalid "
                f"JSON for {key}."
            ) from exc

    missing_markers = (
        "404",
        "Not Found",
        "NoSuchKey",
    )

    if any(
        marker in result.stderr
        for marker in missing_markers
    ):
        return None

    raise RuntimeError(
        f"HeadObject failed for {key}.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def expected_metadata(
    *,
    manifest: dict[str, Any],
    object_kind: str,
    sha256_hex: str,
    table_name: str | None,
    row_count: int | None,
    column_count: int | None,
) -> dict[str, str]:
    metadata = {
        "object-kind": object_kind,
        "source-system": (
            manifest[
                "source_system"
            ]
        ),
        "source-snapshot-id": (
            manifest[
                "source_snapshot_id"
            ]
        ),
        "generated-snapshot-id": (
            manifest[
                "generated_snapshot_id"
            ]
        ),
        "representation": (
            manifest[
                "representation"
            ]
        ),
        "transformation-name": (
            manifest[
                "transformation"
            ][
                "name"
            ]
        ),
        "transformation-version": (
            manifest[
                "transformation"
            ][
                "version"
            ]
        ),
        "sha256": sha256_hex,
    }

    if table_name is not None:
        metadata[
            "table-name"
        ] = table_name

    if row_count is not None:
        metadata[
            "row-count"
        ] = str(
            row_count
        )

    if column_count is not None:
        metadata[
            "column-count"
        ] = str(
            column_count
        )

    if (
        object_kind
        == "query-compatible-manifest"
    ):
        metadata[
            "dataset-count"
        ] = str(
            manifest[
                "dataset_count"
            ]
        )

        metadata[
            "total-data-rows"
        ] = str(
            manifest[
                "total_data_rows"
            ]
        )

        metadata[
            "total-size-bytes"
        ] = str(
            manifest[
                "total_output_size_bytes"
            ]
        )

    return metadata


def verify_head(
    *,
    head: dict[str, Any],
    key: str,
    expected_size: int,
    expected_sha256_hex: str,
    expected_content_type: str,
    expected_object_metadata: dict[
        str,
        str
    ],
) -> dict[str, Any]:
    observed_metadata = {
        str(metadata_key).lower(): str(
            value
        )
        for metadata_key, value in (
            head.get(
                "Metadata",
                {}
            ).items()
        )
    }

    expected_checksum = (
        sha256_base64(
            expected_sha256_hex
        )
    )

    checks = {
        "content_length": (
            head.get(
                "ContentLength"
            )
            == expected_size
        ),
        "checksum_sha256": (
            head.get(
                "ChecksumSHA256"
            )
            == expected_checksum
        ),
        "server_side_encryption": (
            head.get(
                "ServerSideEncryption"
            )
            == "AES256"
        ),
        "content_type": (
            head.get(
                "ContentType"
            )
            == expected_content_type
        ),
        "metadata": (
            observed_metadata
            == expected_object_metadata
        ),
        "version_id": (
            bool(
                head.get(
                    "VersionId"
                )
            )
            and head.get(
                "VersionId"
            )
            != "null"
        ),
    }

    failed_checks = [
        name
        for name, passed
        in checks.items()
        if not passed
    ]

    if failed_checks:
        raise RuntimeError(
            "S3 verification failed for "
            f"{key}: {failed_checks}.\n"
            f"Observed HeadObject:\n"
            f"{json.dumps(head, indent=2)}"
        )

    return {
        "key": key,
        "content_length": (
            head["ContentLength"]
        ),
        "sha256": (
            expected_sha256_hex
        ),
        "checksum_sha256_base64": (
            head["ChecksumSHA256"]
        ),
        "checksum_type": head.get(
            "ChecksumType"
        ),
        "server_side_encryption": (
            head["ServerSideEncryption"]
        ),
        "version_id": (
            head["VersionId"]
        ),
        "etag": head.get("ETag"),
        "last_modified": head.get(
            "LastModified"
        ),
        "content_type": (
            head["ContentType"]
        ),
        "metadata": (
            observed_metadata
        ),
    }


def put_object(
    *,
    source_path: Path,
    bucket: str,
    key: str,
    account_id: str,
    region: str,
    sha256_hex: str,
    content_type: str,
    metadata: dict[str, str],
) -> dict[str, Any]:
    result = run(
        aws_s3_command(
            "put-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--body",
            str(source_path),
            "--checksum-algorithm",
            "SHA256",
            "--checksum-sha256",
            sha256_base64(
                sha256_hex
            ),
            "--server-side-encryption",
            "AES256",
            "--content-type",
            content_type,
            "--metadata",
            json.dumps(
                metadata,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "--if-none-match",
            "*",
            account_id=account_id,
            region=region,
        ),
        check=False,
    )

    if result.returncode == 0:
        try:
            return json.loads(
                result.stdout
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "PutObject returned invalid "
                f"JSON for {key}."
            ) from exc

    if (
        "PreconditionFailed"
        in result.stderr
        or "412" in result.stderr
    ):
        return {
            "precondition_failed": True,
        }

    raise RuntimeError(
        f"PutObject failed for {key}.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def build_specs(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    generated_root: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    dataset_specs: list[
        dict[str, Any]
    ] = []

    for dataset in manifest[
        "datasets"
    ]:
        dataset_specs.append(
            {
                "object_kind": (
                    "query-compatible-dataset"
                ),
                "table_name": (
                    dataset[
                        "table_name"
                    ]
                ),
                "source_path": (
                    generated_root
                    / dataset[
                        "local_relative_path"
                    ]
                ),
                "key": (
                    dataset[
                        "destination_key"
                    ]
                ),
                "size_bytes": (
                    dataset[
                        "output_size_bytes"
                    ]
                ),
                "sha256": (
                    dataset[
                        "output_sha256"
                    ]
                ),
                "row_count": (
                    dataset[
                        "row_count"
                    ]
                ),
                "column_count": len(
                    dataset[
                        "columns"
                    ]
                ),
                "content_type": (
                    "application/x-ndjson"
                ),
            }
        )

    manifest_spec = {
        "object_kind": (
            "query-compatible-manifest"
        ),
        "table_name": None,
        "source_path": manifest_path,
        "key": (
            manifest[
                "manifest_destination_key"
            ]
        ),
        "size_bytes": (
            manifest_path.stat().st_size
        ),
        "sha256": (
            sha256_file(
                manifest_path
            )
        ),
        "row_count": None,
        "column_count": None,
        "content_type": (
            "application/json"
        ),
    }

    return dataset_specs, manifest_spec


def list_snapshot_keys(
    *,
    bucket: str,
    prefix: str,
    account_id: str,
    region: str,
) -> set[str]:
    response = run_json(
        aws_s3_command(
            "list-objects-v2",
            "--bucket",
            bucket,
            "--prefix",
            f"{prefix}/",
            account_id=account_id,
            region=region,
        )
    )

    if response.get(
        "IsTruncated"
    ):
        raise RuntimeError(
            "Snapshot listing was "
            "unexpectedly truncated."
        )

    return {
        item["Key"]
        for item in response.get(
            "Contents",
            [],
        )
    }


def process_object(
    *,
    spec: dict[str, Any],
    manifest: dict[str, Any],
    execute: bool,
    bucket: str,
    account_id: str,
    region: str,
) -> dict[str, Any]:
    metadata = expected_metadata(
        manifest=manifest,
        object_kind=(
            spec[
                "object_kind"
            ]
        ),
        sha256_hex=(
            spec["sha256"]
        ),
        table_name=(
            spec["table_name"]
        ),
        row_count=(
            spec["row_count"]
        ),
        column_count=(
            spec["column_count"]
        ),
    )

    existing = head_object(
        bucket=bucket,
        key=spec["key"],
        account_id=account_id,
        region=region,
    )

    if existing is not None:
        verified = verify_head(
            head=existing,
            key=spec["key"],
            expected_size=(
                spec["size_bytes"]
            ),
            expected_sha256_hex=(
                spec["sha256"]
            ),
            expected_content_type=(
                spec["content_type"]
            ),
            expected_object_metadata=(
                metadata
            ),
        )

        return {
            **verified,
            "object_kind": (
                spec[
                    "object_kind"
                ]
            ),
            "table_name": (
                spec["table_name"]
            ),
            "row_count": (
                spec["row_count"]
            ),
            "column_count": (
                spec["column_count"]
            ),
            "action": (
                "verified-existing"
            ),
            "verified_at_utc": (
                iso_utc(
                    utc_now()
                )
            ),
        }

    if not execute:
        return {
            "object_kind": (
                spec[
                    "object_kind"
                ]
            ),
            "table_name": (
                spec["table_name"]
            ),
            "key": spec["key"],
            "content_length": (
                spec["size_bytes"]
            ),
            "sha256": (
                spec["sha256"]
            ),
            "checksum_sha256_base64": (
                sha256_base64(
                    spec["sha256"]
                )
            ),
            "content_type": (
                spec[
                    "content_type"
                ]
            ),
            "metadata": metadata,
            "row_count": (
                spec["row_count"]
            ),
            "column_count": (
                spec["column_count"]
            ),
            "action": "planned",
        }

    put_response = put_object(
        source_path=(
            spec["source_path"]
        ),
        bucket=bucket,
        key=spec["key"],
        account_id=account_id,
        region=region,
        sha256_hex=(
            spec["sha256"]
        ),
        content_type=(
            spec["content_type"]
        ),
        metadata=metadata,
    )

    uploaded = head_object(
        bucket=bucket,
        key=spec["key"],
        account_id=account_id,
        region=region,
    )

    if uploaded is None:
        raise RuntimeError(
            "Object was not found after "
            f"PutObject: {spec['key']}"
        )

    verified = verify_head(
        head=uploaded,
        key=spec["key"],
        expected_size=(
            spec["size_bytes"]
        ),
        expected_sha256_hex=(
            spec["sha256"]
        ),
        expected_content_type=(
            spec["content_type"]
        ),
        expected_object_metadata=metadata,
    )

    action = "uploaded"

    if put_response.get(
        "precondition_failed"
    ):
        action = (
            "verified-existing-race"
        )

    return {
        **verified,
        "object_kind": (
            spec["object_kind"]
        ),
        "table_name": (
            spec["table_name"]
        ),
        "row_count": (
            spec["row_count"]
        ),
        "column_count": (
            spec["column_count"]
        ),
        "action": action,
        "verified_at_utc": (
            iso_utc(
                utc_now()
            )
        ),
    }


def write_evidence(
    *,
    evidence_root: Path,
    started_at: datetime,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    bucket: str,
    account_id: str,
    region: str,
    objects: list[dict[str, Any]],
) -> Path:
    completed_at = utc_now()

    run_id = (
        "bronze-query-compatible-olist-"
        + started_at.strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )

    evidence_directory = (
        evidence_root
        / run_id
    )

    evidence_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    action_counts: dict[
        str,
        int
    ] = {}

    for item in objects:
        action = item["action"]

        action_counts[action] = (
            action_counts.get(
                action,
                0,
            )
            + 1
        )

    evidence = {
        "schema_version": "1.0",
        "overall_status": "PASS",
        "run_id": run_id,
        "mode": "execute",
        "started_at_utc": (
            iso_utc(
                started_at
            )
        ),
        "completed_at_utc": (
            iso_utc(
                completed_at
            )
        ),
        "aws": {
            "account_id": account_id,
            "identity_arn": (
                identity["Arn"]
            ),
            "region": region,
            "bucket": bucket,
        },
        "source": {
            "source_snapshot_id": (
                manifest[
                    "source_snapshot_id"
                ]
            ),
            "generated_snapshot_id": (
                manifest[
                    "generated_snapshot_id"
                ]
            ),
            "manifest_path": (
                manifest_path.as_posix()
            ),
            "manifest_sha256": (
                sha256_file(
                    manifest_path
                )
            ),
            "representation": (
                manifest[
                    "representation"
                ]
            ),
            "dataset_count": (
                manifest[
                    "dataset_count"
                ]
            ),
            "total_data_rows": (
                manifest[
                    "total_data_rows"
                ]
            ),
            "total_output_size_bytes": (
                manifest[
                    "total_output_size_bytes"
                ]
            ),
            "preserved_multiline_records": (
                manifest[
                    "total_records_with_embedded_breaks"
                ]
            ),
        },
        "destination": {
            "prefix": (
                manifest[
                    "destination_prefix"
                ]
            ),
            "manifest_key": (
                manifest[
                    "manifest_destination_key"
                ]
            ),
            "expected_object_count": (
                manifest[
                    "dataset_count"
                ]
                + 1
            ),
        },
        "summary": {
            "verified_object_count": (
                len(objects)
            ),
            "action_counts": (
                action_counts
            ),
        },
        "objects": objects,
    }

    json_path = (
        evidence_directory
        / "query-compatible-ingestion-evidence.json"
    )

    json_path.write_text(
        json.dumps(
            evidence,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown_lines = [
        "# Olist Query-Compatible Bronze Evidence",
        "",
        "- Overall status: **PASS**",
        f"- Run ID: `{run_id}`",
        (
            "- Raw source snapshot: "
            f"`{manifest['source_snapshot_id']}`"
        ),
        (
            "- Generated snapshot: "
            f"`{manifest['generated_snapshot_id']}`"
        ),
        (
            "- Representation: "
            f"`{manifest['representation']}`"
        ),
        (
            "- Dataset objects: "
            f"**{manifest['dataset_count']}**"
        ),
        "- Manifest objects: **1**",
        (
            "- Total rows: "
            f"**{manifest['total_data_rows']}**"
        ),
        (
            "- Total bytes: "
            f"**{manifest['total_output_size_bytes']}**"
        ),
        (
            "- Preserved multiline records: "
            f"**{manifest['total_records_with_embedded_breaks']}**"
        ),
        (
            "- Verified S3 objects: "
            f"**{len(objects)}**"
        ),
        "",
        "## Objects",
        "",
        (
            "| Object | Action | Bytes | "
            "Version ID | SHA-256 |"
        ),
        "|---|---:|---:|---|---|",
    ]

    for item in objects:
        markdown_lines.append(
            "| "
            f"`{item['key']}` | "
            f"{item['action']} | "
            f"{item['content_length']} | "
            f"`{item['version_id']}` | "
            f"`{item['sha256']}` |"
        )

    markdown_path = (
        evidence_directory
        / "query-compatible-ingestion-evidence.md"
    )

    markdown_path.write_text(
        "\n".join(
            markdown_lines
        )
        + "\n",
        encoding="utf-8",
    )

    return evidence_directory


def main() -> int:
    options = parse_args()
    started_at = utc_now()

    manifest = validate_manifest(
        manifest_path=(
            options.manifest
        ),
        generated_root=(
            options.generated_root
        ),
    )

    if options.execute:
        if (
            options.confirm_generated_snapshot_id
            != manifest[
                "generated_snapshot_id"
            ]
        ):
            raise RuntimeError(
                "--execute requires "
                "--confirm-generated-snapshot-id "
                "with the exact generated "
                "snapshot ID."
            )
    elif (
        options.confirm_generated_snapshot_id
        is not None
    ):
        raise RuntimeError(
            "--confirm-generated-snapshot-id "
            "is only valid with --execute."
        )

    identity = run_json(
        [
            "aws",
            "sts",
            "get-caller-identity",
            "--output",
            "json",
            "--no-cli-pager",
        ]
    )

    if (
        identity.get("Account")
        != options.account_id
    ):
        raise RuntimeError(
            "Authenticated AWS account "
            f"{identity.get('Account')} does "
            "not match expected account "
            f"{options.account_id}."
        )

    versioning = run_json(
        aws_s3_command(
            "get-bucket-versioning",
            "--bucket",
            options.bucket,
            account_id=(
                options.account_id
            ),
            region=options.region,
        )
    )

    if (
        versioning.get("Status")
        != "Enabled"
    ):
        raise RuntimeError(
            "Destination bucket versioning "
            "is not Enabled."
        )

    encryption = run_json(
        aws_s3_command(
            "get-bucket-encryption",
            "--bucket",
            options.bucket,
            account_id=(
                options.account_id
            ),
            region=options.region,
        )
    )

    algorithms = {
        rule[
            "ApplyServerSideEncryptionByDefault"
        ][
            "SSEAlgorithm"
        ]
        for rule in (
            encryption[
                "ServerSideEncryptionConfiguration"
            ][
                "Rules"
            ]
        )
    }

    if algorithms != {"AES256"}:
        raise RuntimeError(
            "Expected only AES256 bucket "
            f"encryption; observed "
            f"{sorted(algorithms)}."
        )

    dataset_specs, manifest_spec = (
        build_specs(
            manifest=manifest,
            manifest_path=(
                options.manifest
            ),
            generated_root=(
                options.generated_root
            ),
        )
    )

    all_specs = [
        *dataset_specs,
        manifest_spec,
    ]

    expected_keys = {
        spec["key"]
        for spec in all_specs
    }

    initial_keys = list_snapshot_keys(
        bucket=options.bucket,
        prefix=manifest[
            "destination_prefix"
        ],
        account_id=(
            options.account_id
        ),
        region=options.region,
    )

    unexpected_keys = (
        initial_keys
        - expected_keys
    )

    if unexpected_keys:
        raise RuntimeError(
            "Unexpected objects under the "
            "generated snapshot prefix: "
            f"{sorted(unexpected_keys)}"
        )

    completion_manifest_key = manifest[
        "manifest_destination_key"
    ]

    if (
        completion_manifest_key
        in initial_keys
        and initial_keys
        != expected_keys
    ):
        missing_keys = (
            expected_keys
            - initial_keys
        )

        raise RuntimeError(
            "The completion manifest exists, "
            "but the generated snapshot is "
            "incomplete. Missing keys: "
            f"{sorted(missing_keys)}"
        )

    results: list[
        dict[str, Any]
    ] = []

    for spec in dataset_specs:
        result = process_object(
            spec=spec,
            manifest=manifest,
            execute=options.execute,
            bucket=options.bucket,
            account_id=(
                options.account_id
            ),
            region=options.region,
        )

        results.append(
            result
        )

        print(
            f"[{result['action'].upper():>17}] "
            f"{result['key']}"
        )

    manifest_result = process_object(
        spec=manifest_spec,
        manifest=manifest,
        execute=options.execute,
        bucket=options.bucket,
        account_id=(
            options.account_id
        ),
        region=options.region,
    )

    results.append(
        manifest_result
    )

    print(
        f"[{manifest_result['action'].upper():>17}] "
        f"{manifest_result['key']}"
    )

    print()
    print(
        "[PASS] Generated manifest and all "
        "nine local JSONL datasets verified."
    )
    print(
        "[PASS] Deterministic generated "
        "snapshot ID verified."
    )
    print(
        "[PASS] Preserved multiline records: "
        f"{manifest['total_records_with_embedded_breaks']}"
    )
    print(
        "[PASS] AWS account: "
        f"{options.account_id}"
    )
    print(
        "[PASS] AWS identity: "
        f"{identity['Arn']}"
    )
    print(
        "[PASS] AWS region: "
        f"{options.region}"
    )
    print(
        "[PASS] Bucket versioning: Enabled"
    )
    print(
        "[PASS] Bucket encryption: AES256"
    )
    print(
        "[PASS] Unexpected generated "
        "snapshot objects: 0"
    )

    if not options.execute:
        existing_count = sum(
            item["action"]
            == "verified-existing"
            for item in results
        )

        planned_count = sum(
            item["action"]
            == "planned"
            for item in results
        )

        print()
        print("Mode: DRY RUN")
        print(
            "Existing verified objects: "
            f"{existing_count}"
        )
        print(
            "Objects planned for upload: "
            f"{planned_count}"
        )
        print(
            "Dataset objects planned: "
            f"{manifest['dataset_count']}"
        )
        print(
            "Manifest objects planned: 1"
        )
        print(
            "Total generated rows: "
            f"{manifest['total_data_rows']}"
        )
        print(
            "Total generated bytes: "
            f"{manifest['total_output_size_bytes']}"
        )
        print(
            "S3 writes performed: 0"
        )

        return 0

    final_keys = list_snapshot_keys(
        bucket=options.bucket,
        prefix=manifest[
            "destination_prefix"
        ],
        account_id=(
            options.account_id
        ),
        region=options.region,
    )

    if final_keys != expected_keys:
        raise RuntimeError(
            "Final S3 key set does not match "
            "the generated manifest."
        )

    evidence_directory = write_evidence(
        evidence_root=(
            options.evidence_root
        ),
        started_at=started_at,
        identity=identity,
        manifest=manifest,
        manifest_path=(
            options.manifest
        ),
        bucket=options.bucket,
        account_id=(
            options.account_id
        ),
        region=options.region,
        objects=results,
    )

    print()
    print("Mode: EXECUTE")
    print(
        "Verified S3 objects: "
        f"{len(results)}"
    )
    print(
        "Snapshot objects expected: "
        f"{len(expected_keys)}"
    )
    print(
        "Snapshot objects observed: "
        f"{len(final_keys)}"
    )
    print(
        "Evidence directory: "
        f"{evidence_directory}"
    )
    print(
        "Overall status: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
