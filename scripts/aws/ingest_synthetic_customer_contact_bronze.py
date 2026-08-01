#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import ingest_olist_query_compatible_bronze as shared


EXPECTED_MANIFEST_SHA256 = (
    "0bd76ea319996dc2b6661fe1018e4033"
    "80bf2dde71339e916c2bbf6242fd1539"
)

EXPECTED_SOURCE_SNAPSHOT_ID = (
    "43cc5e9c8436f7919491dd90872d6f4d"
    "94d61d4694c1d4307e41456e405052d2"
)

EXPECTED_GENERATED_SNAPSHOT_ID = (
    "1b7972218afd4016928dfb185f7eff30"
    "dd2a612384b357beae24bf8daac44e2c"
)

EXPECTED_SOURCE_SYSTEM = (
    "olist-derived-synthetic-supporting"
)

EXPECTED_DATASET_CLASS = (
    "generated_supporting_data"
)

EXPECTED_TABLE_NAME = (
    "synthetic_customer_contact"
)

EXPECTED_DATASET_COUNT = 1
EXPECTED_TOTAL_ROWS = 99441
EXPECTED_TOTAL_BYTES = 30976008

EXPECTED_CSV_BYTES = 10466274
EXPECTED_JSONL_BYTES = 20509734

EXPECTED_CSV_SHA256 = (
    "06f3d4d7fe3511e90e511abbb2c04a72"
    "d01309009a8c3cf239a116a7781cac65"
)

EXPECTED_JSONL_SHA256 = (
    "9585db5f832eafdfff201262037de50cf"
    "2713bdb5b7f83366ddc150988e535c4"
)

EXPECTED_COLUMNS = [
    {
        "name": "customer_id",
        "type": "string",
    },
    {
        "name": "synthetic_email",
        "type": "string",
    },
    {
        "name": "synthetic_phone",
        "type": "string",
    },
    {
        "name": "marketing_consent",
        "type": "boolean",
    },
    {
        "name": "pii_classification",
        "type": "string",
    },
]

EXPECTED_COLUMN_NAMES = [
    column["name"]
    for column in EXPECTED_COLUMNS
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Checksum-verified and idempotent "
            "upload of the deterministic "
            "synthetic customer-contact "
            "supporting Bronze snapshot."
        )
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "manifests/bronze/supporting/"
            "synthetic-customer-contact-"
            "manifest.json"
        ),
    )

    parser.add_argument(
        "--generated-root",
        type=Path,
        required=True,
        help=(
            "Generated snapshot directory "
            "containing source/ and tables/."
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
            "Perform S3 writes. Without this "
            "flag the command is read-only."
        ),
    )

    parser.add_argument(
        "--confirm-generated-snapshot-id",
        help=(
            "Required with --execute and must "
            "match the generated snapshot ID."
        ),
    )

    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(
            "evidence/"
            "bronze-supporting-ingestion"
        ),
    )

    return parser.parse_args()


def require_safe_relative_path(
    relative_name: str,
) -> Path:
    relative_path = Path(
        relative_name
    )

    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise RuntimeError(
            "Manifest local paths must be "
            "safe relative paths."
        )

    return relative_path


def validate_csv(
    file_name: Path,
) -> dict[str, int]:
    customer_ids: set[str] = set()
    emails: set[str] = set()
    phones: set[str] = set()

    consent_true = 0
    consent_false = 0
    row_count = 0

    with file_name.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        reader = csv.DictReader(
            stream
        )

        if (
            reader.fieldnames
            != EXPECTED_COLUMN_NAMES
        ):
            raise RuntimeError(
                "Unexpected supporting CSV "
                "columns."
            )

        for row in reader:
            row_count += 1

            customer_id = (
                row["customer_id"].strip()
            )

            email = (
                row["synthetic_email"].strip()
            )

            phone = (
                row["synthetic_phone"].strip()
            )

            consent = (
                row["marketing_consent"]
                .strip()
            )

            classification = (
                row["pii_classification"]
                .strip()
            )

            if not all(
                [
                    customer_id,
                    email,
                    phone,
                    consent,
                    classification,
                ]
            ):
                raise RuntimeError(
                    "Empty supporting CSV value."
                )

            if consent == "True":
                consent_true += 1
            elif consent == "False":
                consent_false += 1
            else:
                raise RuntimeError(
                    "Unexpected CSV consent value."
                )

            if classification != "PII":
                raise RuntimeError(
                    "Unexpected PII classification."
                )

            customer_ids.add(
                customer_id
            )

            emails.add(
                email
            )

            phones.add(
                phone
            )

    if row_count != EXPECTED_TOTAL_ROWS:
        raise RuntimeError(
            "Unexpected supporting CSV rows."
        )

    if not (
        len(customer_ids)
        == len(emails)
        == len(phones)
        == EXPECTED_TOTAL_ROWS
    ):
        raise RuntimeError(
            "Supporting CSV uniqueness "
            "validation failed."
        )

    if (
        consent_true != 74553
        or consent_false != 24888
    ):
        raise RuntimeError(
            "Unexpected consent distribution."
        )

    return {
        "row_count": row_count,
        "consent_true": consent_true,
        "consent_false": consent_false,
    }


def validate_jsonl(
    file_name: Path,
) -> dict[str, int]:
    row_count = 0
    consent_true = 0
    consent_false = 0

    with file_name.open(
        "r",
        encoding="utf-8",
    ) as stream:
        for line_number, line in enumerate(
            stream,
            start=1,
        ):
            try:
                record = json.loads(
                    line
                )
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    "Invalid JSONL at line "
                    f"{line_number}."
                ) from error

            if (
                list(record)
                != EXPECTED_COLUMN_NAMES
            ):
                raise RuntimeError(
                    "Unexpected JSONL fields or "
                    f"ordering at line "
                    f"{line_number}."
                )

            for field_name in [
                "customer_id",
                "synthetic_email",
                "synthetic_phone",
                "pii_classification",
            ]:
                if not isinstance(
                    record[field_name],
                    str,
                ):
                    raise RuntimeError(
                        f"{field_name} must be "
                        "a JSON string."
                    )

            if not isinstance(
                record["marketing_consent"],
                bool,
            ):
                raise RuntimeError(
                    "marketing_consent must be "
                    "a JSON Boolean."
                )

            if (
                record["pii_classification"]
                != "PII"
            ):
                raise RuntimeError(
                    "Unexpected JSONL "
                    "classification."
                )

            if record["marketing_consent"]:
                consent_true += 1
            else:
                consent_false += 1

            row_count += 1

    if row_count != EXPECTED_TOTAL_ROWS:
        raise RuntimeError(
            "Unexpected supporting JSONL rows."
        )

    if (
        consent_true != 74553
        or consent_false != 24888
    ):
        raise RuntimeError(
            "Unexpected JSONL consent "
            "distribution."
        )

    return {
        "row_count": row_count,
        "consent_true": consent_true,
        "consent_false": consent_false,
    }


def validate_manifest(
    *,
    manifest_path: Path,
    generated_root: Path,
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing manifest: "
            f"{manifest_path}"
        )

    if (
        shared.sha256_file(
            manifest_path
        )
        != EXPECTED_MANIFEST_SHA256
    ):
        raise RuntimeError(
            "Unexpected supporting manifest "
            "SHA-256."
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    expected_values = {
        "schema_version": "1.0",
        "source_system": (
            EXPECTED_SOURCE_SYSTEM
        ),
        "dataset_class": (
            EXPECTED_DATASET_CLASS
        ),
        "source_snapshot_id": (
            EXPECTED_SOURCE_SNAPSHOT_ID
        ),
        "generated_snapshot_id": (
            EXPECTED_GENERATED_SNAPSHOT_ID
        ),
        "representation": (
            "athena-json-lines"
        ),
        "dataset_count": (
            EXPECTED_DATASET_COUNT
        ),
        "total_data_rows": (
            EXPECTED_TOTAL_ROWS
        ),
        "total_output_size_bytes": (
            EXPECTED_TOTAL_BYTES
        ),
    }

    for key, expected_value in (
        expected_values.items()
    ):
        if (
            manifest.get(key)
            != expected_value
        ):
            raise RuntimeError(
                f"Unexpected manifest value: "
                f"{key}."
            )

    expected_serde = {
        "library": (
            shared.EXPECTED_SERDE_LIBRARY
        ),
        "input_format": (
            shared.EXPECTED_INPUT_FORMAT
        ),
        "output_format": (
            shared.EXPECTED_OUTPUT_FORMAT
        ),
    }

    if (
        manifest.get("serde")
        != expected_serde
    ):
        raise RuntimeError(
            "Unexpected supporting SerDe."
        )

    governance = manifest.get(
        "governance",
        {},
    )

    if (
        governance.get("synthetic")
        is not True
        or governance.get(
            "contains_real_pii"
        )
        is not False
        or governance.get(
            "contains_simulated_pii"
        )
        is not True
    ):
        raise RuntimeError(
            "Unexpected supporting governance "
            "classification."
        )

    destination_prefix = (
        "bronze/generated/supporting/"
        "synthetic-customer-contact/"
        "snapshots/"
        f"{EXPECTED_GENERATED_SNAPSHOT_ID}"
    )

    if (
        manifest.get(
            "destination_prefix"
        )
        != destination_prefix
    ):
        raise RuntimeError(
            "Unexpected supporting destination "
            "prefix."
        )

    expected_manifest_key = (
        f"{destination_prefix}/"
        "synthetic-customer-contact-"
        "manifest.json"
    )

    if (
        manifest.get(
            "manifest_destination_key"
        )
        != expected_manifest_key
    ):
        raise RuntimeError(
            "Unexpected supporting manifest "
            "destination key."
        )

    source_artifact = manifest.get(
        "source_artifact",
        {},
    )

    expected_source_relative = Path(
        "source/"
        "synthetic_customer_contact.csv"
    )

    source_relative = (
        require_safe_relative_path(
            source_artifact.get(
                "local_relative_path",
                "",
            )
        )
    )

    if (
        source_relative
        != expected_source_relative
    ):
        raise RuntimeError(
            "Unexpected supporting CSV "
            "relative path."
        )

    source_file = (
        generated_root
        / source_relative
    )

    expected_source_key = (
        f"{destination_prefix}/"
        "source/"
        "synthetic_customer_contact.csv"
    )

    if (
        source_artifact.get(
            "destination_key"
        )
        != expected_source_key
    ):
        raise RuntimeError(
            "Unexpected supporting CSV "
            "destination key."
        )

    if (
        source_artifact.get(
            "output_size_bytes"
        )
        != EXPECTED_CSV_BYTES
        or source_artifact.get(
            "output_sha256"
        )
        != EXPECTED_CSV_SHA256
    ):
        raise RuntimeError(
            "Unexpected supporting CSV "
            "manifest checksum or size."
        )

    if not source_file.is_file():
        raise FileNotFoundError(
            f"Missing supporting CSV: "
            f"{source_file}"
        )

    if (
        source_file.stat().st_size
        != EXPECTED_CSV_BYTES
        or shared.sha256_file(
            source_file
        )
        != EXPECTED_CSV_SHA256
    ):
        raise RuntimeError(
            "Local supporting CSV does not "
            "match the manifest."
        )

    validate_csv(
        source_file
    )

    datasets = manifest.get(
        "datasets",
        [],
    )

    if len(datasets) != 1:
        raise RuntimeError(
            "Expected exactly one supporting "
            "dataset."
        )

    dataset = datasets[0]

    if (
        dataset.get("table_name")
        != EXPECTED_TABLE_NAME
        or dataset.get("row_count")
        != EXPECTED_TOTAL_ROWS
        or dataset.get(
            "physical_line_count"
        )
        != EXPECTED_TOTAL_ROWS
        or dataset.get(
            "column_count"
        )
        != len(EXPECTED_COLUMNS)
        or dataset.get("columns")
        != EXPECTED_COLUMNS
        or dataset.get("primary_key")
        != ["customer_id"]
        or dataset.get(
            "output_size_bytes"
        )
        != EXPECTED_JSONL_BYTES
        or dataset.get(
            "output_sha256"
        )
        != EXPECTED_JSONL_SHA256
    ):
        raise RuntimeError(
            "Unexpected supporting dataset "
            "definition."
        )

    expected_jsonl_relative = Path(
        "tables/"
        "synthetic_customer_contact/"
        "data.jsonl"
    )

    jsonl_relative = (
        require_safe_relative_path(
            dataset.get(
                "local_relative_path",
                "",
            )
        )
    )

    if (
        jsonl_relative
        != expected_jsonl_relative
    ):
        raise RuntimeError(
            "Unexpected supporting JSONL "
            "relative path."
        )

    jsonl_file = (
        generated_root
        / jsonl_relative
    )

    expected_jsonl_key = (
        f"{destination_prefix}/"
        "tables/"
        "synthetic_customer_contact/"
        "data.jsonl"
    )

    expected_jsonl_location = (
        "s3://${data_lake_bucket}/"
        f"{destination_prefix}/"
        "tables/"
        "synthetic_customer_contact/"
    )

    if (
        dataset.get(
            "destination_key"
        )
        != expected_jsonl_key
        or dataset.get(
            "destination_location"
        )
        != expected_jsonl_location
    ):
        raise RuntimeError(
            "Unexpected supporting JSONL "
            "destination."
        )

    if not jsonl_file.is_file():
        raise FileNotFoundError(
            f"Missing supporting JSONL: "
            f"{jsonl_file}"
        )

    if (
        jsonl_file.stat().st_size
        != EXPECTED_JSONL_BYTES
        or shared.sha256_file(
            jsonl_file
        )
        != EXPECTED_JSONL_SHA256
    ):
        raise RuntimeError(
            "Local supporting JSONL does not "
            "match the manifest."
        )

    validate_jsonl(
        jsonl_file
    )

    if (
        source_file.stat().st_size
        + jsonl_file.stat().st_size
        != EXPECTED_TOTAL_BYTES
    ):
        raise RuntimeError(
            "Calculated supporting bytes do "
            "not match the manifest."
        )

    return manifest


def expected_metadata(
    *,
    manifest: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, str]:
    governance = manifest[
        "governance"
    ]

    metadata = {
        "object-kind": (
            spec["object_kind"]
        ),
        "source-system": (
            manifest["source_system"]
        ),
        "dataset-class": (
            manifest["dataset_class"]
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
            manifest["representation"]
        ),
        "synthetic": str(
            governance["synthetic"]
        ).lower(),
        "contains-real-pii": str(
            governance[
                "contains_real_pii"
            ]
        ).lower(),
        "contains-simulated-pii": str(
            governance[
                "contains_simulated_pii"
            ]
        ).lower(),
        "sha256": spec["sha256"],
    }

    if spec["table_name"] is not None:
        metadata["table-name"] = (
            spec["table_name"]
        )

    if spec["row_count"] is not None:
        metadata["row-count"] = str(
            spec["row_count"]
        )

    if spec["column_count"] is not None:
        metadata["column-count"] = str(
            spec["column_count"]
        )

    if (
        spec["object_kind"]
        == "supporting-manifest"
    ):
        metadata["dataset-count"] = str(
            manifest["dataset_count"]
        )

        metadata["total-data-rows"] = str(
            manifest["total_data_rows"]
        )

        metadata["total-size-bytes"] = str(
            manifest[
                "total_output_size_bytes"
            ]
        )

    return metadata


def build_specs(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    generated_root: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    source_artifact = manifest[
        "source_artifact"
    ]

    dataset = manifest[
        "datasets"
    ][0]

    data_specs = [
        {
            "object_kind": (
                "supporting-source-csv"
            ),
            "table_name": (
                EXPECTED_TABLE_NAME
            ),
            "source_path": (
                generated_root
                / source_artifact[
                    "local_relative_path"
                ]
            ),
            "key": (
                source_artifact[
                    "destination_key"
                ]
            ),
            "size_bytes": (
                source_artifact[
                    "output_size_bytes"
                ]
            ),
            "sha256": (
                source_artifact[
                    "output_sha256"
                ]
            ),
            "row_count": (
                EXPECTED_TOTAL_ROWS
            ),
            "column_count": (
                len(EXPECTED_COLUMNS)
            ),
            "content_type": "text/csv",
        },
        {
            "object_kind": (
                "supporting-dataset"
            ),
            "table_name": (
                dataset["table_name"]
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
                dataset["row_count"]
            ),
            "column_count": len(
                dataset["columns"]
            ),
            "content_type": (
                "application/x-ndjson"
            ),
        },
    ]

    manifest_spec = {
        "object_kind": (
            "supporting-manifest"
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
        "sha256": shared.sha256_file(
            manifest_path
        ),
        "row_count": None,
        "column_count": None,
        "content_type": (
            "application/json"
        ),
    }

    return data_specs, manifest_spec


def verified_result(
    *,
    verified: dict[str, Any],
    spec: dict[str, Any],
    action: str,
) -> dict[str, Any]:
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
            shared.iso_utc(
                shared.utc_now()
            )
        ),
    }


def planned_result(
    *,
    spec: dict[str, Any],
    metadata: dict[str, str],
) -> dict[str, Any]:
    return {
        "object_kind": (
            spec["object_kind"]
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
            shared.sha256_base64(
                spec["sha256"]
            )
        ),
        "content_type": (
            spec["content_type"]
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
        spec=spec,
    )

    existing = shared.head_object(
        bucket=bucket,
        key=spec["key"],
        account_id=account_id,
        region=region,
    )

    if existing is not None:
        verified = shared.verify_head(
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

        return verified_result(
            verified=verified,
            spec=spec,
            action="verified-existing",
        )

    if not execute:
        return planned_result(
            spec=spec,
            metadata=metadata,
        )

    put_response = shared.put_object(
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

    uploaded = shared.head_object(
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

    verified = shared.verify_head(
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

    return verified_result(
        verified=verified,
        spec=spec,
        action=action,
    )


def build_action_counts(
    objects: list[dict[str, Any]],
) -> dict[str, int]:
    action_counts: dict[str, int] = {}

    for item in objects:
        action = item["action"]

        action_counts[action] = (
            action_counts.get(
                action,
                0,
            )
            + 1
        )

    return action_counts


def build_evidence_payload(
    *,
    started_at: datetime,
    completed_at: datetime,
    run_id: str,
    identity: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    bucket: str,
    account_id: str,
    region: str,
    objects: list[dict[str, Any]],
) -> dict[str, Any]:
    action_counts = build_action_counts(
        objects
    )

    return {
        "schema_version": "1.0",
        "overall_status": "PASS",
        "run_id": run_id,
        "mode": "execute",
        "started_at_utc": (
            shared.iso_utc(
                started_at
            )
        ),
        "completed_at_utc": (
            shared.iso_utc(
                completed_at
            )
        ),
        "aws": {
            "account_id": account_id,
            "identity_arn": identity["Arn"],
            "region": region,
            "bucket": bucket,
        },
        "source": {
            "source_system": (
                manifest["source_system"]
            ),
            "dataset_class": (
                manifest["dataset_class"]
            ),
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
                shared.sha256_file(
                    manifest_path
                )
            ),
            "representation": (
                manifest["representation"]
            ),
            "dataset_count": (
                manifest["dataset_count"]
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
            "governance": (
                manifest["governance"]
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
            "expected_object_count": 3,
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


def build_evidence_markdown(
    *,
    evidence: dict[str, Any],
) -> str:
    source = evidence["source"]
    summary = evidence["summary"]

    markdown_lines = [
        (
            "# Synthetic Customer-Contact "
            "Bronze Ingestion Evidence"
        ),
        "",
        (
            "- Overall status: "
            f"**{evidence['overall_status']}**"
        ),
        (
            "- Run ID: "
            f"`{evidence['run_id']}`"
        ),
        (
            "- AWS account: "
            f"`{evidence['aws']['account_id']}`"
        ),
        (
            "- AWS region: "
            f"`{evidence['aws']['region']}`"
        ),
        (
            "- S3 bucket: "
            f"`{evidence['aws']['bucket']}`"
        ),
        (
            "- Source system: "
            f"`{source['source_system']}`"
        ),
        (
            "- Dataset class: "
            f"`{source['dataset_class']}`"
        ),
        (
            "- Source snapshot: "
            f"`{source['source_snapshot_id']}`"
        ),
        (
            "- Generated snapshot: "
            f"`{source['generated_snapshot_id']}`"
        ),
        (
            "- Representation: "
            f"`{source['representation']}`"
        ),
        (
            "- Dataset rows: "
            f"**{source['total_data_rows']}**"
        ),
        (
            "- Dataset and source bytes: "
            f"**{source['total_output_size_bytes']}**"
        ),
        (
            "- Verified S3 objects: "
            f"**{summary['verified_object_count']}**"
        ),
        (
            "- Contains real PII: "
            f"**{source['governance']['contains_real_pii']}**"
        ),
        (
            "- Contains simulated PII: "
            f"**{source['governance']['contains_simulated_pii']}**"
        ),
        "",
        "## Action counts",
        "",
    ]
    for action, count in sorted(
        summary[
            "action_counts"
        ].items()
    ):
        markdown_lines.append(
            f"- `{action}`: **{count}**"
        )

    markdown_lines.extend(
        [
            "",
            "## Objects",
            "",
            (
                "| Object | Kind | Action | "
                "Bytes | Version ID | SHA-256 |"
            ),
            (
                "|---|---|---:|---:|---|---|"
            ),
        ]
    )

    for item in evidence["objects"]:
        markdown_lines.append(
            "| "
            f"`{item['key']}` | "
            f"`{item['object_kind']}` | "
            f"{item['action']} | "
            f"{item['content_length']} | "
            f"`{item.get('version_id', 'n/a')}` | "
            f"`{item['sha256']}` |"
        )

    return (
        "\n".join(markdown_lines)
        + "\n"
    )


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
    completed_at = shared.utc_now()

    run_id = (
        "bronze-supporting-contact-"
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

    evidence = build_evidence_payload(
        started_at=started_at,
        completed_at=completed_at,
        run_id=run_id,
        identity=identity,
        manifest=manifest,
        manifest_path=manifest_path,
        bucket=bucket,
        account_id=account_id,
        region=region,
        objects=objects,
    )

    json_path = (
        evidence_directory
        / "supporting-ingestion-evidence.json"
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

    markdown_path = (
        evidence_directory
        / "supporting-ingestion-evidence.md"
    )

    markdown_path.write_text(
        build_evidence_markdown(
            evidence=evidence,
        ),
        encoding="utf-8",
    )

    return evidence_directory


def validate_execution_mode(
    *,
    options: argparse.Namespace,
    manifest: dict[str, Any],
) -> None:
    generated_snapshot_id = manifest[
        "generated_snapshot_id"
    ]

    if options.execute:
        if (
            options.confirm_generated_snapshot_id
            != generated_snapshot_id
        ):
            raise RuntimeError(
                "--execute requires "
                "--confirm-generated-snapshot-id "
                "with the exact deterministic "
                "generated snapshot ID."
            )

        return

    if (
        options.confirm_generated_snapshot_id
        is not None
    ):
        raise RuntimeError(
            "--confirm-generated-snapshot-id "
            "is only valid with --execute."
        )


def verify_aws_preconditions(
    *,
    options: argparse.Namespace,
) -> dict[str, Any]:
    identity = shared.run_json(
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

    versioning = shared.run_json(
        shared.aws_s3_command(
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

    encryption = shared.run_json(
        shared.aws_s3_command(
            "get-bucket-encryption",
            "--bucket",
            options.bucket,
            account_id=(
                options.account_id
            ),
            region=options.region,
        )
    )

    encryption_rules = encryption.get(
        "ServerSideEncryptionConfiguration",
        {},
    ).get(
        "Rules",
        [],
    )

    algorithms = {
        rule.get(
            "ApplyServerSideEncryptionByDefault",
            {},
        ).get(
            "SSEAlgorithm"
        )
        for rule in encryption_rules
    }

    algorithms.discard(
        None
    )

    if algorithms != {"AES256"}:
        raise RuntimeError(
            "Expected only AES256 bucket "
            "encryption; observed "
            f"{sorted(algorithms)}."
        )

    return identity


def validate_snapshot_key_state(
    *,
    initial_keys: set[str],
    expected_keys: set[str],
    completion_manifest_key: str,
) -> None:
    unexpected_keys = (
        initial_keys
        - expected_keys
    )

    if unexpected_keys:
        raise RuntimeError(
            "Unexpected objects under the "
            "supporting snapshot prefix: "
            f"{sorted(unexpected_keys)}"
        )

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
            "but the supporting snapshot is "
            "incomplete. Missing keys: "
            f"{sorted(missing_keys)}"
        )


def print_object_result(
    result: dict[str, Any],
) -> None:
    print(
        f"[{result['action'].upper():>22}] "
        f"{result['key']}"
    )


def process_snapshot_specs(
    *,
    data_specs: list[dict[str, Any]],
    manifest_spec: dict[str, Any],
    manifest: dict[str, Any],
    options: argparse.Namespace,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for spec in data_specs:
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

        print_object_result(
            result
        )

    manifest_result = process_object(
        spec=manifest_spec,
        manifest=manifest,
        execute=options.execute,
        bucket=options.bucket,
        account_id=options.account_id,
        region=options.region,
    )

    results.append(
        manifest_result
    )

    print_object_result(
        manifest_result
    )

    return results


def print_common_summary(
    *,
    manifest: dict[str, Any],
    identity: dict[str, Any],
    options: argparse.Namespace,
) -> None:
    print()
    print(
        "[PASS] Supporting manifest, source "
        "CSV and query-compatible JSONL "
        "verified."
    )
    print(
        "[PASS] Generated snapshot ID: "
        f"{manifest['generated_snapshot_id']}"
    )
    print(
        "[PASS] Supporting rows: "
        f"{manifest['total_data_rows']}"
    )
    print(
        "[PASS] Supporting bytes: "
        f"{manifest['total_output_size_bytes']}"
    )
    print(
        "[PASS] Contains real PII: "
        f"{manifest['governance']['contains_real_pii']}"
    )
    print(
        "[PASS] Contains simulated PII: "
        f"{manifest['governance']['contains_simulated_pii']}"
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


def print_dry_run_summary(
    *,
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    existing_count = sum(
        item["action"]
        == "verified-existing"
        for item in results
    )

    planned_count = sum(
        item["action"] == "planned"
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
    print("Source CSV objects: 1")
    print("Dataset JSONL objects: 1")
    print("Completion manifest objects: 1")
    print(
        "Total generated rows: "
        f"{manifest['total_data_rows']}"
    )
    print(
        "Total generated bytes: "
        f"{manifest['total_output_size_bytes']}"
    )
    print("S3 writes performed: 0")


def print_execute_summary(
    *,
    results: list[dict[str, Any]],
    evidence_directory: Path,
) -> None:
    action_counts = build_action_counts(
        results
    )

    print()
    print("Mode: EXECUTE")
    print(
        "Verified S3 objects: "
        f"{len(results)}"
    )
    print(
        "Action counts: "
        f"{json.dumps(action_counts, sort_keys=True)}"
    )
    print(
        "Evidence directory: "
        f"{evidence_directory}"
    )


def main() -> int:
    options = parse_args()
    started_at = shared.utc_now()

    manifest = validate_manifest(
        manifest_path=(
            options.manifest
        ),
        generated_root=(
            options.generated_root
        ),
    )

    validate_execution_mode(
        options=options,
        manifest=manifest,
    )

    identity = verify_aws_preconditions(
        options=options,
    )

    data_specs, manifest_spec = (
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
        *data_specs,
        manifest_spec,
    ]

    expected_keys = {
        spec["key"]
        for spec in all_specs
    }

    initial_keys = (
        shared.list_snapshot_keys(
            bucket=options.bucket,
            prefix=manifest[
                "destination_prefix"
            ],
            account_id=(
                options.account_id
            ),
            region=options.region,
        )
    )

    validate_snapshot_key_state(
        initial_keys=initial_keys,
        expected_keys=expected_keys,
        completion_manifest_key=(
            manifest[
                "manifest_destination_key"
            ]
        ),
    )

    results = process_snapshot_specs(
        data_specs=data_specs,
        manifest_spec=manifest_spec,
        manifest=manifest,
        options=options,
    )

    print_common_summary(
        manifest=manifest,
        identity=identity,
        options=options,
    )

    if not options.execute:
        print_dry_run_summary(
            manifest=manifest,
            results=results,
        )

        return 0

    final_keys = (
        shared.list_snapshot_keys(
            bucket=options.bucket,
            prefix=manifest[
                "destination_prefix"
            ],
            account_id=(
                options.account_id
            ),
            region=options.region,
        )
    )

    if final_keys != expected_keys:
        raise RuntimeError(
            "Final S3 key set does not "
            "match the supporting manifest."
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
        account_id=options.account_id,
        region=options.region,
        objects=results,
    )

    print_execute_summary(
        results=results,
        evidence_directory=(
            evidence_directory
        ),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
