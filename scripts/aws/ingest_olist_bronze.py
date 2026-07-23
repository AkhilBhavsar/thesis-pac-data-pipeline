#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]

EXPECTED_DATASET_COUNT = 9
EXPECTED_TOTAL_SIZE_BYTES = 126186995
EXPECTED_TOTAL_DATA_ROWS = 1550922


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic, checksum-verified and "
            "idempotent Olist Bronze ingestion."
        )
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "manifests/bronze/olist/"
            "source-manifest.json"
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
        "--confirm-snapshot-id",
        help=(
            "Required with --execute and must exactly "
            "match the manifest snapshot ID."
        ),
    )

    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(
            "evidence/bronze-ingestion"
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


def sha256_base64_from_hex(
    sha256_hex: str,
) -> str:
    return base64.b64encode(
        bytes.fromhex(
            sha256_hex
        )
    ).decode("ascii")


def inspect_csv(
    path: Path,
) -> tuple[int, list[str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.reader(handle)
        columns = next(reader, None)

        if columns is None:
            raise RuntimeError(
                f"CSV is empty: {path}"
            )

        row_count = sum(
            1 for _ in reader
        )

    return row_count, columns


def validate_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise RuntimeError(
            "Manifest does not exist: "
            f"{manifest_path}"
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    datasets = manifest.get(
        "datasets",
        [],
    )

    observed_files = [
        item["filename"]
        for item in datasets
    ]

    if observed_files != EXPECTED_FILES:
        raise RuntimeError(
            "Unexpected Olist file set "
            "or manifest ordering."
        )

    if (
        manifest.get("dataset_count")
        != EXPECTED_DATASET_COUNT
    ):
        raise RuntimeError(
            "Manifest dataset_count "
            f"must be {EXPECTED_DATASET_COUNT}."
        )

    if (
        manifest.get(
            "total_size_bytes"
        )
        != EXPECTED_TOTAL_SIZE_BYTES
    ):
        raise RuntimeError(
            "Manifest total_size_bytes "
            "does not match the fixed source."
        )

    if (
        manifest.get(
            "total_data_rows"
        )
        != EXPECTED_TOTAL_DATA_ROWS
    ):
        raise RuntimeError(
            "Manifest total_data_rows "
            "does not match the fixed source."
        )

    snapshot_id = manifest[
        "snapshot_id"
    ]

    expected_prefix = (
        "bronze/raw/olist/snapshots/"
        f"{snapshot_id}"
    )

    if (
        manifest.get(
            "destination_prefix"
        )
        != expected_prefix
    ):
        raise RuntimeError(
            "destination_prefix does not "
            "match snapshot_id."
        )

    expected_manifest_key = (
        f"{expected_prefix}/"
        "source-manifest.json"
    )

    if (
        manifest.get(
            "manifest_destination_key"
        )
        != expected_manifest_key
    ):
        raise RuntimeError(
            "manifest_destination_key "
            "is invalid."
        )

    total_bytes = 0
    total_rows = 0
    canonical_datasets: list[
        dict[str, Any]
    ] = []

    for item in datasets:
        source_path = Path(
            item[
                "relative_source_path"
            ]
        )

        if not source_path.is_file():
            raise RuntimeError(
                "Missing source file: "
                f"{source_path}"
            )

        row_count, columns = inspect_csv(
            source_path
        )

        observed_values = {
            "size_bytes": (
                source_path.stat().st_size
            ),
            "sha256": sha256_file(
                source_path
            ),
            "row_count": row_count,
            "column_count": len(
                columns
            ),
            "columns": columns,
            "destination_key": (
                f"{expected_prefix}/"
                f"{item['filename']}"
            ),
        }

        for field, observed_value in (
            observed_values.items()
        ):
            expected_value = item.get(
                field
            )

            if (
                expected_value
                != observed_value
            ):
                raise RuntimeError(
                    f"{item['filename']} "
                    f"mismatch for {field}: "
                    f"expected="
                    f"{expected_value!r}, "
                    f"observed="
                    f"{observed_value!r}"
                )

        total_bytes += observed_values[
            "size_bytes"
        ]

        total_rows += row_count

        canonical_datasets.append(
            {
                "filename": (
                    item["filename"]
                ),
                "size_bytes": (
                    observed_values[
                        "size_bytes"
                    ]
                ),
                "row_count": row_count,
                "column_count": len(
                    columns
                ),
                "columns": columns,
                "sha256": observed_values[
                    "sha256"
                ],
            }
        )

    if (
        total_bytes
        != manifest[
            "total_size_bytes"
        ]
    ):
        raise RuntimeError(
            "Calculated total source bytes "
            "do not match the manifest."
        )

    if (
        total_rows
        != manifest[
            "total_data_rows"
        ]
    ):
        raise RuntimeError(
            "Calculated total source rows "
            "do not match the manifest."
        )

    snapshot_basis = {
        "schema_version": (
            manifest[
                "schema_version"
            ]
        ),
        "source_system": (
            manifest[
                "source_system"
            ]
        ),
        "datasets": canonical_datasets,
    }

    canonical_payload = json.dumps(
        snapshot_basis,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    observed_snapshot_id = (
        hashlib.sha256(
            canonical_payload
        ).hexdigest()
    )

    if (
        observed_snapshot_id
        != snapshot_id
    ):
        raise RuntimeError(
            "snapshot_id does not match "
            "the canonical source metadata."
        )

    return manifest


def head_object(
    *,
    bucket: str,
    key: str,
    account_id: str,
    region: str,
) -> dict[str, Any] | None:
    command = aws_s3_command(
        "head-object",
        "--bucket",
        bucket,
        "--key",
        key,
        "--checksum-mode",
        "ENABLED",
        account_id=account_id,
        region=region,
    )

    result = run(
        command,
        check=False,
    )

    if result.returncode == 0:
        try:
            return json.loads(
                result.stdout
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "HeadObject returned "
                f"invalid JSON for {key}."
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
    filename: str,
    row_count: int | None = None,
    column_count: int | None = None,
) -> dict[str, str]:
    metadata = {
        "object-kind": object_kind,
        "snapshot-id": (
            manifest[
                "snapshot_id"
            ]
        ),
        "source-system": (
            manifest[
                "source_system"
            ]
        ),
        "source-filename": filename,
        "sha256": sha256_hex,
    }

    if row_count is not None:
        metadata[
            "row-count"
        ] = str(row_count)

    if column_count is not None:
        metadata[
            "column-count"
        ] = str(column_count)

    if object_kind == "source-manifest":
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
                "total_size_bytes"
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
    expected_checksum = (
        sha256_base64_from_hex(
            expected_sha256_hex
        )
    )

    observed_metadata = {
        str(key_name).lower(): str(
            value
        )
        for key_name, value in (
            head.get(
                "Metadata",
                {}
            ).items()
        )
    }

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
        check_name
        for check_name, passed
        in checks.items()
        if not passed
    ]

    if failed_checks:
        raise RuntimeError(
            f"S3 verification failed for "
            f"{key}: {failed_checks}.\n"
            f"Observed HeadObject:\n"
            f"{json.dumps(head, indent=2)}"
        )

    return {
        "key": key,
        "content_length": head[
            "ContentLength"
        ],
        "checksum_sha256_base64": (
            head[
                "ChecksumSHA256"
            ]
        ),
        "checksum_type": head.get(
            "ChecksumType"
        ),
        "sha256": (
            expected_sha256_hex
        ),
        "etag": head.get("ETag"),
        "version_id": head[
            "VersionId"
        ],
        "last_modified": head.get(
            "LastModified"
        ),
        "server_side_encryption": (
            head[
                "ServerSideEncryption"
            ]
        ),
        "content_type": head[
            "ContentType"
        ],
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
    checksum_base64 = (
        sha256_base64_from_hex(
            sha256_hex
        )
    )

    command = aws_s3_command(
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
        checksum_base64,
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
    )

    result = run(
        command,
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


def build_object_specs(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
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
                "object_kind": "dataset",
                "filename": (
                    dataset[
                        "filename"
                    ]
                ),
                "source_path": Path(
                    dataset[
                        "relative_source_path"
                    ]
                ),
                "key": dataset[
                    "destination_key"
                ],
                "size_bytes": dataset[
                    "size_bytes"
                ],
                "sha256": dataset[
                    "sha256"
                ],
                "row_count": dataset[
                    "row_count"
                ],
                "column_count": dataset[
                    "column_count"
                ],
                "content_type": (
                    "text/csv"
                ),
            }
        )

    manifest_sha256 = sha256_file(
        manifest_path
    )

    manifest_spec = {
        "object_kind": (
            "source-manifest"
        ),
        "filename": (
            manifest_path.name
        ),
        "source_path": (
            manifest_path
        ),
        "key": manifest[
            "manifest_destination_key"
        ],
        "size_bytes": (
            manifest_path.stat().st_size
        ),
        "sha256": manifest_sha256,
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
            "Snapshot prefix listing "
            "was unexpectedly truncated."
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
    object_metadata = (
        expected_metadata(
            manifest=manifest,
            object_kind=(
                spec[
                    "object_kind"
                ]
            ),
            sha256_hex=(
                spec["sha256"]
            ),
            filename=(
                spec["filename"]
            ),
            row_count=(
                spec["row_count"]
            ),
            column_count=(
                spec[
                    "column_count"
                ]
            ),
        )
    )

    existing_head = head_object(
        bucket=bucket,
        key=spec["key"],
        account_id=account_id,
        region=region,
    )

    if existing_head is not None:
        verified = verify_head(
            head=existing_head,
            key=spec["key"],
            expected_size=(
                spec["size_bytes"]
            ),
            expected_sha256_hex=(
                spec["sha256"]
            ),
            expected_content_type=(
                spec[
                    "content_type"
                ]
            ),
            expected_object_metadata=(
                object_metadata
            ),
        )

        return {
            **verified,
            "object_kind": (
                spec[
                    "object_kind"
                ]
            ),
            "filename": (
                spec["filename"]
            ),
            "row_count": (
                spec["row_count"]
            ),
            "column_count": (
                spec[
                    "column_count"
                ]
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
            "filename": (
                spec["filename"]
            ),
            "key": spec["key"],
            "content_length": (
                spec["size_bytes"]
            ),
            "sha256": (
                spec["sha256"]
            ),
            "checksum_sha256_base64": (
                sha256_base64_from_hex(
                    spec["sha256"]
                )
            ),
            "content_type": (
                spec[
                    "content_type"
                ]
            ),
            "metadata": (
                object_metadata
            ),
            "row_count": (
                spec["row_count"]
            ),
            "column_count": (
                spec[
                    "column_count"
                ]
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
        sha256_hex=spec[
            "sha256"
        ],
        content_type=spec[
            "content_type"
        ],
        metadata=object_metadata,
    )

    uploaded_head = head_object(
        bucket=bucket,
        key=spec["key"],
        account_id=account_id,
        region=region,
    )

    if uploaded_head is None:
        raise RuntimeError(
            "Object was not found after "
            f"PutObject: {spec['key']}"
        )

    verified = verify_head(
        head=uploaded_head,
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
            object_metadata
        ),
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
        "filename": (
            spec["filename"]
        ),
        "row_count": (
            spec["row_count"]
        ),
        "column_count": (
            spec[
                "column_count"
            ]
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
    manifest_sha256: str,
    bucket: str,
    account_id: str,
    region: str,
    objects: list[
        dict[str, Any]
    ],
) -> Path:
    completed_at = utc_now()

    run_id = (
        "bronze-olist-"
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
            "account_id": (
                account_id
            ),
            "identity_arn": (
                identity["Arn"]
            ),
            "region": region,
            "bucket": bucket,
        },
        "source": {
            "source_system": (
                manifest[
                    "source_system"
                ]
            ),
            "snapshot_id": (
                manifest[
                    "snapshot_id"
                ]
            ),
            "manifest_path": (
                manifest_path.as_posix()
            ),
            "manifest_sha256": (
                manifest_sha256
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
            "total_size_bytes": (
                manifest[
                    "total_size_bytes"
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
        / "bronze-ingestion-evidence.json"
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
        "# Olist Bronze Ingestion Evidence",
        "",
        f"- Overall status: **PASS**",
        (
            "- Run ID: "
            f"`{run_id}`"
        ),
        (
            "- Snapshot ID: "
            f"`{manifest['snapshot_id']}`"
        ),
        (
            "- AWS account: "
            f"`{account_id}`"
        ),
        (
            "- AWS region: "
            f"`{region}`"
        ),
        (
            "- S3 bucket: "
            f"`{bucket}`"
        ),
        (
            "- Dataset objects: "
            f"**{manifest['dataset_count']}**"
        ),
        "- Manifest objects: **1**",
        (
            "- Total source rows: "
            f"**{manifest['total_data_rows']}**"
        ),
        (
            "- Total source bytes: "
            f"**{manifest['total_size_bytes']}**"
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
        (
            "|---|---:|---:|---|---|"
        ),
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
        / "bronze-ingestion-evidence.md"
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
        options.manifest
    )

    if options.execute:
        if (
            options.confirm_snapshot_id
            != manifest["snapshot_id"]
        ):
            raise RuntimeError(
                "--execute requires "
                "--confirm-snapshot-id with "
                "the exact manifest snapshot ID."
            )
    elif (
        options.confirm_snapshot_id
        is not None
    ):
        raise RuntimeError(
            "--confirm-snapshot-id is only "
            "valid with --execute."
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
            "Authenticated account "
            f"{identity.get('Account')} "
            "does not match expected "
            f"account {options.account_id}."
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
            "encryption; observed "
            f"{sorted(algorithms)}."
        )

    dataset_specs, manifest_spec = (
        build_object_specs(
            manifest=manifest,
            manifest_path=(
                options.manifest
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
            "content-addressed snapshot prefix: "
            f"{sorted(unexpected_keys)}"
        )

    manifest_key = manifest[
        "manifest_destination_key"
    ]

    if (
        manifest_key in initial_keys
        and initial_keys != expected_keys
    ):
        missing_keys = (
            expected_keys
            - initial_keys
        )

        raise RuntimeError(
            "The completion manifest exists, "
            "but the snapshot is incomplete. "
            "Missing keys: "
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

        results.append(result)

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
        "[PASS] Local source manifest "
        "matches all 9 CSV files."
    )
    print(
        "[PASS] Snapshot ID matches "
        "canonical source metadata."
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
        "[PASS] Unexpected snapshot objects: 0"
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
        print("Manifest objects planned: 1")
        print(
            "Total source rows: "
            f"{manifest['total_data_rows']}"
        )
        print(
            "Total source bytes: "
            f"{manifest['total_size_bytes']}"
        )
        print("S3 writes performed: 0")

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
            "Final S3 key set does not "
            "match the manifest. "
            f"Expected={sorted(expected_keys)}, "
            f"observed={sorted(final_keys)}"
        )

    manifest_sha256 = sha256_file(
        options.manifest
    )

    evidence_directory = (
        write_evidence(
            evidence_root=(
                options.evidence_root
            ),
            started_at=started_at,
            identity=identity,
            manifest=manifest,
            manifest_path=(
                options.manifest
            ),
            manifest_sha256=(
                manifest_sha256
            ),
            bucket=options.bucket,
            account_id=(
                options.account_id
            ),
            region=options.region,
            objects=results,
        )
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
    print("Overall status: PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
